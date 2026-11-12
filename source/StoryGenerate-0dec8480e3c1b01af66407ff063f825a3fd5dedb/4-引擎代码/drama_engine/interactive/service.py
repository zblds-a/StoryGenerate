from __future__ import annotations
import copy
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from .models import Creation, Command, QUICK, BackgroundSpec, fingerprint
from .store import Conflict, emit, now, public
from .prompts import VERSION


class Service:
    def __init__(self, store, images_enabled=False, story_only=False):
        self.store, self.images_enabled, self.story_only = store, images_enabled, story_only

    def create(self, owner, value: Creation, characters):
        if self.story_only and value.output != 'script':
            raise Conflict('STORY_ONLY_OUTPUT_REQUIRED')
        if {c['character_id'] for c in characters} != set(value.character_ids):
            raise Conflict('CHARACTERS_NOT_FOUND')
        for c in characters:
            if not c.get('role_id') or not c.get('performer_id'):
                raise Conflict('CHARACTER_BINDING_REQUIRED')
        source = self.store.get(value.source_session_id, owner) if value.source_session_id else None
        if source and (not source.get('confirmed_version') or source['creation']['form'] != 'series'):
            raise Conflict('CONFIRMED_SERIES_REQUIRED')
        if source and source['episode_number'] >= source['creation']['series_episodes']:
            raise Conflict('SERIES_COMPLETE')
        if source and source['creation']['character_ids'] != value.character_ids:
            raise Conflict('CHARACTER_IDENTITY_CONFLICT')
        if source:
            characters = copy.deepcopy(source['characters'])
        sid = uuid4().hex
        creation = value.model_dump(mode='json')
        if source:
            creation = {**source['creation'], 'idempotency_key': value.idempotency_key,
                        'method': 'continue', 'source_session_id': source['id']}
            if self.story_only:
                creation.update(output='script', casting=None)
        state = dict(id=sid, owner=owner, revision=1, generation_epoch=1, creation=creation,
            characters=characters, created_at=now(), updated_at=now(), last_seq=0, events=[], commands={},
            stage='directions' if creation['method'] == 'assist' else 'outlining',
            work=None, background_work={}, backgrounds={}, scenes=[], scene_keys=[], outline=None,
            directions=[], feedback=[], pending_change=None, history=copy.deepcopy(source['history']) if source else [],
            episode_number=source['episode_number'] + 1 if source else 1,
            episode_id=uuid4().hex, plan_id=uuid4().hex, plan_revision=1,
            story_id=source['story_id'] if source else uuid4().hex,
            series_id=source['series_id'] if source else sid,
            version_no=source['version_no'] + 1 if source else 1,
            parent_story_version_id=source['confirmed_version'] if source else None,
            source_delivery=source['delivery'] if source else None,
            series_outline=source.get('series_outline') if source else None,
            call_records=[], call_count=0, unknown_usage_calls=0,
            prompt_version=VERSION,
            confirmed_version=None, delivery=None, media=None, metrics={'started_at': now()})
        emit(state, 'stage.changed', {'stage': state['stage']})
        return public(self.store.create(owner, value.idempotency_key, fingerprint(value.model_dump()), state))

    def command(self, sid, owner, command: Command):
        digest = fingerprint(command.model_dump())
        def apply(s):
            if self.story_only and s['creation']['output'] != 'script':
                raise Conflict('STORY_ONLY_SESSION_REQUIRED')
            previous = s['commands'].get(command.command_id)
            if previous:
                if previous['hash'] != digest:
                    raise Conflict('IDEMPOTENCY_CONFLICT')
                return previous['result']
            if command.expected_revision != s['revision'] - 1:
                raise Conflict('REVISION_CONFLICT')
            if command.kind not in public(s)['available_actions']:
                raise Conflict('ACTION_NOT_AVAILABLE')
            k = command.kind
            if k == 'cancel':
                s['generation_epoch'] += 1
                s['stage'], s['work'] = 'cancelled', None
                for bg in s['backgrounds'].values():
                    if bg['status'] in ('queued', 'running'):
                        bg['status'] = 'stale'
                emit(s, 'generation.cancelled')
            elif k == 'set_preferences':
                if s['work'] or s.get('source_delivery') or s.get('approved_outline'):
                    raise Conflict('PREFERENCES_FROZEN')
                if command.focus_role_id and command.focus_role_id not in s['creation']['character_ids']:
                    raise Conflict('UNAPPROVED_ROLE')
                if (command.series_episodes is not None or command.series_ending is not None) and s['creation']['form'] != 'series':
                    raise Conflict('SERIES_REQUIRED')
                if command.ending is None and command.series_ending is None and not command.focus_role_id and command.series_episodes is None:
                    raise Conflict('PREFERENCES_REQUIRED')
                if command.ending is not None:
                    s['creation']['ending'] = command.ending
                if command.series_ending is not None:
                    s['creation']['series_ending'] = command.series_ending
                if command.series_episodes is not None:
                    s['creation']['series_episodes'] = command.series_episodes
                if command.focus_role_id:
                    s['feedback'].append('突出角色 ' + command.focus_role_id + ' 的目标、选择与成长')
                s['generation_epoch'] += 1
                s['plan_id'], s['plan_revision'] = uuid4().hex, s['plan_revision'] + 1
                s['stage'] = 'outlining'
                emit(s, 'change.applied', {'scope': 'outline', 'ending': s['creation']['ending'],
                    'series_episodes': s['creation']['series_episodes'], 'focus_role_id': command.focus_role_id})
            elif k == 'select_direction':
                d = next((d for d in s['directions'] if d['id'] == command.target_id), None)
                if not d:
                    raise Conflict('DIRECTION_NOT_FOUND')
                s['direction'], s['stage'] = d, 'outlining'
            elif k in ('revise_outline', 'change'):
                text = self.feedback(s, command)
                pending = s['pending_change'] or {'instructions': [], 'start': len(s['scenes']), 'scope': command.scope}
                if command.target_id:
                    if command.target_id not in s['scene_keys']:
                        raise Conflict('SCENE_NOT_FOUND')
                    start = s['scene_keys'].index(command.target_id)
                else:
                    start = len(s['scenes'])
                    if s['work'] and s['work']['kind'] == 'scene':
                        start += 1  # No target means future scenes; explicit current key rewrites current scene.
                    start = min(start, max(0, len(s['scene_keys']) - 1))
                pending['start'] = min(pending['start'], start)
                pending['scope'] = 'following' if pending['scope'] != command.scope else command.scope
                if text not in pending['instructions']:
                    pending['instructions'].append(text)
                s['pending_change'] = pending
                emit(s, 'change.accepted', {'pending': pending, 'status': 'waiting_boundary' if s['work'] else 'accepted'})
                if not s['work']:
                    if s['stage'] == 'outline_ready':
                        self.apply_outline_feedback(s)
                    elif s['stage'] in ('script_ready', 'confirmed', 'media_ready', 'failed'):
                        s['stage'] = 'change_ready'
                        emit(s, 'change.proposed', pending)
            elif k == 'confirm_change':
                pending = s['pending_change']
                if not pending or command.fingerprint != fingerprint(pending):
                    raise Conflict('STALE_CHANGE')
                start = pending['start']
                s['generation_epoch'] += 1
                s['feedback'].extend(pending['instructions'])
                s['change_scope'] = pending['scope']
                s['change_start'] = start
                s['protected_suffix'] = s['scenes'][start + 1:] if pending['scope'] == 'scene' else []
                s['protected_prefix'] = s['scenes'][:start]
                for i in range(start, len(s['scene_keys'])):
                    if pending['scope'] == 'scene' and i > start:
                        break
                    key = s['scene_keys'][i]
                    emit(s, 'scene.invalidated', {'scene_key': key})
                    self.stale_background(s, key)
                s['scenes'] = s['scenes'][:start]
                if s.get('confirmed_version'):
                    s['parent_story_version_id'] = s['confirmed_version']
                    s['version_no'] += 1
                    s['version_history'] = [*s.get('version_history', []),
                        {'delivery': s['delivery'], 'media': s['media'], 'confirmed_at': now()}]
                    s['history'] = [h for h in s['history'] if h['episode_number'] < s['episode_number']]
                s['confirmed_version'], s['media'], s['delivery'] = None, None, None
                s['stage'], s['pending_change'] = 'outlining', None
                s['plan_id'], s['plan_revision'] = uuid4().hex, s['plan_revision'] + 1
                emit(s, 'change.applied', {'start': start, 'scope': pending['scope']})
            elif k == 'confirm_outline':
                if command.target_id != s['plan_id'] or command.fingerprint != s.get('outline_fingerprint') or s['pending_change']:
                    raise Conflict('STALE_OUTLINE')
                s['approved_outline'] = copy.deepcopy(s['outline'])
                s['stage'] = 'writing'
                self.backgrounds(s)
            elif k == 'confirm_script':
                if (s['pending_change'] or command.target_id != s['delivery']['story_version_id']
                        or command.fingerprint != s['script_fingerprint']):
                    raise Conflict('STALE_SCRIPT')
                s['confirmed_version'] = command.target_id
                s['history'] = [*s['history'], {'episode_number': s['episode_number'],
                    'summary': s['delivery']['episodes'][-1].get('episode_summary') or s['delivery']['summary'],
                    'continuity': s['delivery']['continuity_state']}]
                s['stage'] = 'confirmed' if s['creation']['output'] == 'script' else 'media_pending'
                emit(s, 'script.confirmed', {'story_version_id': command.target_id})
            elif k == 'retry_background':
                bg = s['backgrounds'].get(command.target_id)
                if not bg or bg['status'] != 'failed':
                    raise Conflict('BACKGROUND_NOT_RETRYABLE')
                bg['status'] = 'queued' if self.images_enabled else 'disabled'
            elif k == 'retry':
                if s.get('inflight_unknown'):
                    raise Conflict('UNKNOWN_CALL_REQUIRES_RECONCILIATION')
                s['stage'] = s['failed_stage']
                s['error_code'] = None
                s['error_details'] = None
            elif k == 'next_episode':
                # Returned descriptor is consumed by the client to create an idempotent child session.
                if s['creation']['form'] != 'series' or s['episode_number'] >= s['creation']['series_episodes']:
                    raise Conflict('SERIES_COMPLETE')
            emit(s, 'stage.changed', {'stage': s['stage']})
            result = {'command_id': command.command_id, 'status': 'accepted', 'revision': s['revision']}
            if k == 'next_episode':
                result['next_creation'] = {**s['creation'], 'method': 'continue', 'source_session_id': sid,
                                           'idempotency_key': command.command_id}
            s['commands'][command.command_id] = {'hash': digest, 'result': result}
            return result
        state, result = self.store.mutate(sid, owner, apply)
        return {'receipt': result, 'session': public(state)}

    @staticmethod
    def feedback(s, c):
        if c.option_id in QUICK:
            text = QUICK[c.option_id]
        elif c.option_id:
            found = [choice for card in (s.get('outline') or {}).get('scenes', [])
                     for choice in card.get('choices', []) if choice['id'] == c.option_id]
            if not found:
                raise Conflict('OPTION_NOT_FOUND')
            text = found[0]['title'] + '：' + found[0]['premise']
        else:
            text = ''
        if not text and not c.text.strip():
            raise Conflict('FEEDBACK_REQUIRED')
        return (text + ' ' + c.text.strip()).strip()

    @staticmethod
    def apply_outline_feedback(s):
        s['feedback'].extend(s['pending_change']['instructions'])
        s['pending_change'] = None
        s['generation_epoch'] += 1
        s['plan_revision'] += 1
        s['stage'] = 'outlining'

    @staticmethod
    def stale_background(s, key):
        if key in s['backgrounds']:
            s['backgrounds'][key]['status'] = 'stale'
            emit(s, 'background.stale', {'scene_key': key})

    def backgrounds(self, s):
        for i, card in enumerate(s['outline']['scenes']):
            key = s['scene_keys'][i]
            old = s['backgrounds'].get(key)
            if i < len(s['scenes']) and old and old['status'] == 'ready':
                continue
            spec = BackgroundSpec(scene_key=key, revision=(old['spec']['revision'] + 1) if old else 1,
                plan_id=s['plan_id'], generation_epoch=s['generation_epoch'],
                **{k: card[k] for k in ('location', 'time_of_day', 'environment', 'atmosphere', 'must_include', 'must_avoid')},
                art_style=s['creation']['art_style'], prompt=card['background_prompt'] +
                '。统一' + s['creation']['art_style'] + '风格，纯环境，前景留白，不含人物、文字或水印。').model_dump(mode='json')
            # Cache by content, not scene identity/epoch.
            digest = fingerprint({k: v for k, v in spec.items() if k not in ('scene_key', 'revision', 'generation_epoch', 'plan_id')})
            if old and old['hash'] == digest and old['status'] == 'ready':
                old['spec'] = spec
                continue
            s['backgrounds'][key] = {'spec': spec, 'hash': digest, 'status': 'queued' if self.images_enabled else 'disabled'}
            emit(s, 'background.spec.ready', {'scene_key': key, **s['backgrounds'][key]})


class Worker:
    """One external work unit per claim. Expired work is never silently replayed."""
    def __init__(self, service, generator_factory, media=None, images=None):
        self.service, self.store = service, service.store
        self.generator_factory, self.media, self.images = generator_factory, media, images

    def run_once(self):
        for snapshot in self.store.all():
            if self.service.story_only and snapshot['creation']['output'] != 'script':
                continue  # Do not claim legacy media sessions in the story-only worker.
            if snapshot['stage'] not in ('directions', 'outlining', 'writing', 'media_pending'):
                continue
            sid, owner = snapshot['id'], snapshot['owner']
            token = uuid4().hex
            def claim(s):
                if s['work']:
                    if s['work']['expires_at'] < now():
                        s['inflight_unknown'] = True
                        s['failed_stage'], s['stage'] = s['stage'], 'failed'
                        s['error_code'] = 'WORKER_RESULT_UNKNOWN'
                        s['work'] = None
                        emit(s, 'generation.failed', {'code': s['error_code']})
                    return False
                if s['stage'] != snapshot['stage']:
                    return False
                kind = {'directions': 'directions', 'outlining': 'outline', 'media_pending': 'media'}.get(s['stage'],
                    'scene' if len(s['scenes']) < len(s['scene_keys']) else 'finalize')
                if s['pending_change'] and kind in ('scene', 'finalize'):
                    s['stage'] = 'change_ready'
                    emit(s, 'change.proposed', {**s['pending_change'], 'fingerprint': fingerprint(s['pending_change'])})
                    return False
                s['work'] = {'token': token, 'kind': kind, 'epoch': s['generation_epoch'],
                    'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}
                if kind == 'scene':
                    emit(s, 'scene.started', {'scene_key': s['scene_keys'][len(s['scenes'])]})
                return True
            state, claimed = self.store.mutate(sid, owner, claim)
            if not claimed:
                continue
            kind = state['work']['kind']
            try:
                generator = self.generator_factory() if kind != 'media' else None
                if kind == 'media':
                    if not self.media:
                        raise ValueError('MEDIA_NOT_CONFIGURED')
                    result = self.media(copy.deepcopy(state), 'session:' + sid + ':' + state['confirmed_version'])
                else:
                    provider = getattr(generator, 'provider', None)
                    if provider:
                        self.guard(provider, sid, owner, token)
                    result = getattr(generator, kind)(state, len(state['scenes'])) if kind == 'scene' else getattr(generator, kind)(state)
                self.finish(sid, owner, token, result)
            except Exception as exc:
                def fail(s):
                    if not s['work'] or s['work']['token'] != token:
                        return
                    s['failed_stage'], s['stage'], s['work'] = s['stage'], 'failed', None
                    # Never publish arbitrary vendor text or credentials.
                    code = str(exc)
                    s['error_code'] = code if code.isascii() and code.replace('_', '').isalnum() and len(code) < 80 else 'GENERATION_FAILED'
                    if s.get('inflight_unknown'):
                        s['error_code'] = 'EXTERNAL_RESULT_UNKNOWN'
                    s['error_details'] = {'exception_type': type(exc).__name__}
                    if hasattr(exc, 'errors') and callable(exc.errors):
                        s['error_details']['validation'] = [{'location': list(e['loc']), 'type': e['type']} for e in exc.errors()[:8]]
                    emit(s, 'generation.failed', {'code': s['error_code']})
                self.store.mutate(sid, owner, fail)
            return True
        return False

    def guard(self, provider, sid, owner, token):
        original = provider.complete
        provider.max_retries = 0
        chunks = {}
        def preview(attempt, field, text):
            def publish(s):
                work = s['work']
                if not work or work['token'] != token or work['epoch'] != s['generation_epoch']:
                    raise Conflict('EXECUTION_FENCED')
                if work['kind'] not in ('outline', 'scene', 'directions'):
                    return
                chunks[attempt] = chunks.get(attempt, 0) + 1
                payload = {'attempt_id': attempt, 'chunk_index': chunks[attempt], 'field': field, 'text': text}
                if work['kind'] == 'scene':
                    payload['scene_key'] = s['scene_keys'][len(s['scenes'])]
                s['metrics'].setdefault('first_preview_at', now())
                emit(s, 'scene.text.delta' if work['kind'] == 'scene' else 'outline.delta', payload)
            self.store.mutate(sid, owner, publish)
        if hasattr(provider, 'preview'):
            provider.preview = preview
        def complete(spec, system, user, *args, **kwargs):
            def reserve(s):
                if not s['work'] or s['work']['token'] != token or s['stage'] == 'cancelled':
                    raise Conflict('EXECUTION_FENCED')
                if s['call_count'] >= 64 or s.get('inflight_unknown'):
                    raise Conflict('CALL_BUDGET_EXCEEDED')
                s['call_count'] += 1
                s['inflight_unknown'] = True
            reserved, _ = self.store.mutate(sid, owner, reserve)
            start = len(getattr(provider, 'call_history', []))
            try:
                from ..llm.usage_context import usage_scope
                with usage_scope(principal_id=owner, session_id=sid, plan_id=reserved['plan_id'],
                                 request_id='interactive-' + sid, stage='interactive',
                                 generation_epoch=reserved['generation_epoch']):
                    return original(spec, system, user, *args, **kwargs)
            finally:
                records = getattr(provider, 'call_history', [])[start:]
                records = [{**record, 'interactive_prompt_version': VERSION} for record in records]
                def account(s):
                    s['call_records'].extend(records)
                    unknown = not records or any(c.get('usage_source') == 'unavailable' for c in records)
                    s['unknown_usage_calls'] += int(unknown)
                    s['inflight_unknown'] = unknown
                self.store.mutate(sid, owner, account)
        provider.complete = complete

    def finish(self, sid, owner, token, result):
        def apply(s):
            nonlocal result
            work = s['work']
            if not work or work['token'] != token or work['epoch'] != s['generation_epoch']:
                return
            kind = work['kind']
            s['work'] = None
            if kind == 'directions':
                s['directions'] = [{'id': uuid4().hex, **d} for d in result['directions']]
                s['stage'] = 'directions_ready'
            elif kind == 'outline':
                if s['pending_change']:
                    self.service.apply_outline_feedback(s)
                    return
                expected = s['creation']['series_episodes'] if s['creation']['form'] == 'series' else 1
                if len(result['episode_summaries']) != expected:
                    raise ValueError('EPISODE_PLAN_COUNT_MISMATCH')
                if {p['role_id'] for p in result['character_portrayals']} != {c['role_id'] for c in s['characters']}:
                    raise ValueError('OUTLINE_CAST_MISMATCH')
                # Preserve confirmed prefix exactly; a new plan cannot silently rewrite it.
                if s['outline']:
                    prefix = len(s['scenes'])
                    if len(result['scenes']) <= prefix:
                        raise ValueError('OUTLINE_REWRITE_RANGE_MISSING')
                    result['scenes'][:prefix] = copy.deepcopy(s['outline']['scenes'][:prefix])
                    if s.get('change_scope') == 'scene':
                        result['scenes'] = [*s['outline']['scenes'][:prefix], result['scenes'][prefix],
                                            *s['outline']['scenes'][prefix + 1:]]
                keys = s['scene_keys']
                s['scene_keys'] = [keys[i] if i < len(keys) else uuid4().hex for i in range(len(result['scenes']))]
                for card in result['scenes']:
                    for choice in card['choices']:
                        choice.setdefault('id', uuid4().hex)
                s['outline'] = result
                series = copy.deepcopy(result)
                if s.get('series_outline') and s['episode_number'] > 1:
                    count = s['episode_number'] - 1
                    series['episode_summaries'][:count] = s['series_outline']['episode_summaries'][:count]
                s['series_outline'] = series
                s['outline_fingerprint'] = fingerprint({'outline': result, 'characters': s['characters'],
                    'plan_revision': s['plan_revision'], 'creation': s['creation']})
                s['stage'] = 'outline_ready'
                s['metrics'].setdefault('outline_ready_at', now())
                emit(s, 'outline.ready', {'outline': result, 'plan_id': s['plan_id'], 'fingerprint': s['outline_fingerprint']})
            elif kind == 'scene':
                s['scenes'].append(result)
                s['metrics'].setdefault('first_scene_ready_at', now())
                emit(s, 'scene.ready', {'scene_key': result['scene']['scene_id'], **result})
                if s.get('protected_suffix'):
                    s['scenes'].extend(s.pop('protected_suffix'))
                if s['pending_change']:
                    s['stage'] = 'change_ready'
                    emit(s, 'change.proposed', {**s['pending_change'], 'fingerprint': fingerprint(s['pending_change'])})
            elif kind == 'finalize':
                if s['pending_change']:
                    s['stage'] = 'change_ready'
                    emit(s, 'change.proposed', {**s['pending_change'], 'fingerprint': fingerprint(s['pending_change'])})
                    return
                if 'delivery' in result:
                    for replacement in result.get('scene_updates', []):
                        key = replacement['scene']['scene_id']
                        index = s['scene_keys'].index(key)
                        emit(s, 'scene.invalidated', {'scene_key': key, 'reason': 'targeted_duration_repair'})
                        s['scenes'][index] = replacement
                        emit(s, 'scene.ready', {'scene_key': key, **replacement})
                    result = result['delivery']
                s['delivery'], s['stage'] = result, 'script_ready'
                s['script_fingerprint'] = fingerprint(result)
                s['metrics']['script_ready_at'] = now()
                emit(s, 'script.ready', {'story_version_id': result['story_version_id'], 'fingerprint': s['script_fingerprint']})
            elif kind == 'media':
                s['media'], s['stage'] = result, 'media_ready'
                emit(s, 'media.started', result)
            emit(s, 'stage.changed', {'stage': s['stage']})
        self.store.mutate(sid, owner, apply)
