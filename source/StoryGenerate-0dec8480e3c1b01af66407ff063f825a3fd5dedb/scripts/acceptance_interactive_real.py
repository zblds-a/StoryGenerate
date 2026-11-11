"""Explicit paid-model acceptance; credentials only from process environment.

Run --probe before --scenario. Raw story artifacts stay under the ignored output directory.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import json
import os
import time
import hashlib
from pathlib import Path
import httpx

MODELS = ['deepseek-v4.1-flash-1017', 'qwen/deepseek-v4-pro']


def probe(output):
    url = os.environ['STORY_ACCEPTANCE_BASE_URL'].rstrip('/')
    def one(pair):
        alias, model = pair
        key = os.environ['STORY_ASSET_' + alias.upper()]
        started = time.monotonic()
        result = {'asset': alias, 'model': model}
        try:
            response = httpx.post(url + '/chat/completions', headers={'Authorization': 'Bearer ' + key},
                json={'model': model, 'messages': [{'role': 'user', 'content': 'Return exactly this JSON object: {"ok":true}'}],
                      'temperature': 0, 'max_tokens': 100}, timeout=120, trust_env=False)
            result['http_status'] = response.status_code
            if response.is_success:
                data = response.json()
                result.update(actual_model=data.get('model'), content=data.get('choices', [{}])[0].get('message', {}).get('content'),
                              usage=data.get('usage'), provider_request_id=data.get('id'))
            else:
                result['error'] = 'HTTP_' + str(response.status_code)
        except Exception as exc:
            result['error'] = type(exc).__name__
        result['elapsed_sec'] = round(time.monotonic() - started, 3)
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(one, [(a, m) for a in ('a', 'b') for m in MODELS]))
    output.mkdir(parents=True, exist_ok=True)
    (output/'probe.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=['short', 'mystery', 'fantasy', 'adventure', 'series', 'continue', 'revise', 'outline_edit', 'mid_change', 'cancel'])
    parser.add_argument('--stream', action='store_true')
    parser.add_argument('--source-id')
    parser.add_argument('--resume-id')
    parser.add_argument('--database-url')
    args = parser.parse_args()
    if args.probe:
        probe(args.output)
    if args.case:
        scenario(args)


def scenario(args):
    source_root = Path(__file__).resolve().parents[1] / '4-引擎代码/drama_engine/interactive'
    source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_root.glob('*.py')}
    from sqlalchemy import create_engine
    from drama_engine.interactive.store import Store, public
    from drama_engine.interactive.models import Creation, Command, fingerprint
    from drama_engine.interactive.service import Service, Worker
    from drama_engine.interactive.generator import Generator
    from drama_engine.interactive.streaming import StreamingProvider
    from drama_engine.llm.openai_compat import build_provider_from_env
    args.output.mkdir(parents=True, exist_ok=True)
    run_id = args.case + '-' + str(int(time.time()))
    folder = args.output/run_id
    folder.mkdir()
    engine = create_engine(args.database_url or 'sqlite:///' + str((args.output/'sessions.db').resolve()))
    store = Store(engine)
    store.migrate()
    service = Service(store)
    chars = [dict(character_id=cid, role_id=cid, performer_id='performer-' + cid,
        canon={'name': name, 'immutable_facts': [fact]}, profile={'speech_style': style, 'goal': '和伙伴一起解决眼前困难'})
        for cid, name, fact, style in [('qing', '阿青', '擅长修理小物件', '简短直接，行动前先问清楚'),
                                      ('mo', '小墨', '喜欢记录声音', '温柔细心，喜欢问具体的问题')]]
    count = [0]
    interaction = [False]
    class Recording(StreamingProvider):
        def complete(self, spec, system, user, deadline=None):
            from drama_engine.llm.usage_context import current_usage_context
            count[0] += 1
            original_preview = self.preview
            def preview(attempt, field, value):
                original_preview(attempt, field, value)
                current_sid = current_usage_context().get('session_id')
                if interaction[0] or not current_sid:
                    return
                current = store.get(current_sid, 'acceptance')
                if args.case == 'cancel' and current['stage'] == 'outlining':
                    interaction[0] = True
                    service.command(current_sid, 'acceptance', Command(command_id=run_id+'-cancel-inflight',
                        expected_revision=current['revision'], kind='cancel'))
                elif (args.case == 'mid_change' and current['work']['kind'] == 'scene'
                      and len(current['scenes']) >= 1 and field == 'text'):
                    interaction[0] = True
                    service.command(current_sid, 'acceptance', Command(command_id=run_id+'-change-inflight',
                        expected_revision=current['revision'], kind='change',
                        target_id=current['scene_keys'][len(current['scenes'])], option_id='warmer', scope='following',
                        text='结尾让两位伙伴明确约定第二天一起归还物品。'))
            self.preview = preview
            try:
                result = super().complete(spec, system, user, deadline)
            finally:
                self.preview = original_preview
            (folder/('response-%03d.json' % count[0])).write_text(json.dumps({
                'role': spec.role, 'model': result.model, 'session_id': current_usage_context().get('session_id'),
                'text': result.text}, ensure_ascii=False, indent=2), encoding='utf-8')
            return result
    def factory():
        return Generator(Recording(build_provider_from_env(), lambda *args: None, args.stream))
    worker = Worker(service, factory)
    source = store.get(args.source_id, 'acceptance') if args.source_id else None
    if args.resume_id:
        sid = args.resume_id
    elif args.case == 'revise':
        if not source:
            raise ValueError('--source-id required')
        sid = source['id']
    else:
        value = Creation(idempotency_key=run_id, form='series' if args.case in ('series', 'continue') else 'short',
            method='continue' if args.case == 'continue' else ('assist' if args.case == 'series' else 'idea'),
            source_session_id=args.source_id if args.case == 'continue' else None,
            character_ids=['qing','mo'], output='script',
            genre={'mystery':'悬疑推理','fantasy':'国风奇幻','adventure':'冒险成长'}.get(args.case,'生活治愈'),
            idea='雨夜，小墨把借来的录音笔弄坏了，阿青帮忙修好，两人决定诚实告诉物主。不要新增发声角色。')
        sid = service.create('acceptance', value, chars)['id']
    start = time.monotonic()
    def command(kind, **data):
        state = store.get(sid, 'acceptance')
        return service.command(sid, 'acceptance', Command(command_id=run_id+'-'+kind+'-'+str(state['revision']),
            expected_revision=state['revision'], kind=kind, **data))
    if args.resume_id:
        command('retry')
    if args.case == 'revise':
        command('change', target_id=source['scene_keys'][-1], text='最后一句由小墨说“明天，我们一起把录音笔还回去。”，不要改变之前已完成的场景。', scope='scene')
    adjusted = False
    for step in range(40):
        state = store.get(sid, 'acceptance')
        print(json.dumps({'case': args.case, 'session_id': sid, 'stage': state['stage'],
            'scenes': len(state['scenes']), 'calls': state['call_count'], 'elapsed_sec': round(time.monotonic()-start,1)}), flush=True)
        if state['stage'] in ('failed', 'cancelled', 'confirmed', 'media_ready'):
            break
        if args.case == 'cancel' and state['stage'] == 'outline_ready':
            command('cancel')
        elif state['stage'] == 'directions_ready':
            command('select_direction', target_id=state['directions'][0]['id'])
        elif state['stage'] == 'outline_ready':
            if args.case == 'outline_edit' and not adjusted:
                command('revise_outline', option_id='lighter')
                adjusted = True
            else:
                command('confirm_outline', target_id=state['plan_id'], fingerprint=state['outline_fingerprint'])
        elif state['stage'] == 'change_ready':
            command('confirm_change', fingerprint=fingerprint(state['pending_change']))
        elif state['stage'] == 'script_ready':
            command('confirm_script', target_id=state['delivery']['story_version_id'], fingerprint=state['script_fingerprint'])
        else:
            if not worker.run_once():
                raise ValueError('NO_RUNNABLE_WORK')
    state = store.get(sid, 'acceptance')
    report = {'case': args.case, 'session_id': sid, 'stage': state['stage'], 'error_code': state.get('error_code'),
        'error_details': state.get('error_details'),
        'calls': state['call_count'], 'unknown_usage_calls': state['unknown_usage_calls'], 'elapsed_sec': round(time.monotonic()-start,3),
        'reported_input_tokens': sum(c.get('input_tokens',0) for c in state['call_records'] if c.get('usage_source')=='reported'),
        'reported_output_tokens': sum(c.get('output_tokens',0) for c in state['call_records'] if c.get('usage_source')=='reported'),
        'metrics': state['metrics'], 'stream': args.stream, 'media_calls': 0, 'image_calls': 0,
        'human_content_review': 'not_performed', 'resumed_session': args.resume_id}
    report['inflight_interaction_submitted'] = interaction[0]
    checks = {'terminal_state': state['stage'] == ('cancelled' if args.case == 'cancel' else 'confirmed'),
              'event_sequence': [e['seq'] for e in state['events']] == list(range(1, state['last_seq'] + 1)),
              'no_unconfirmed_media': not any(e['type'] == 'media.started' for e in state['events'])}
    if state['delivery']:
        checks['ready_delivery'] = state['delivery']['status'] == 'READY'
    if args.case in ('series', 'continue') and state['outline']:
        checks['series_six_episode_plan'] = len(state['outline']['episode_summaries']) == 6
        checks['only_current_episode_generated'] = len(state['delivery']['episodes']) == state['episode_number'] if state['delivery'] else False
    if args.case == 'revise' and state['delivery']:
        old = state['version_history'][-1]['delivery']
        checks['protected_prefix_unchanged'] = state['delivery']['episodes'][0]['scenes'][:-1] == old['episodes'][0]['scenes'][:-1]
        lines = [u for e in state['delivery']['episodes'] for s in e['scenes'] for u in s['utterances'] if u['kind']=='dialogue']
        checks['requested_last_line'] = lines[-1]['text'] == '明天，我们一起把录音笔还回去。' and lines[-1]['speaker_role_id'] == 'mo'
    if args.case == 'mid_change':
        checks['changed_during_call'] = interaction[0] and state['generation_epoch'] > 1
        checks['protected_prefix_unchanged'] = state['scenes'][:len(state.get('protected_prefix',[]))] == state.get('protected_prefix')
    report['checks'] = checks
    report['accepted'] = all(checks.values())
    report['source_sha256'] = source_hashes
    (folder/'state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
