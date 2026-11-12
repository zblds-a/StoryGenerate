import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine
from drama_engine.interactive.models import Creation, Command, fingerprint
from drama_engine.interactive.store import Store, Conflict
from drama_engine.interactive.service import Service, Worker


CHARS = [dict(character_id='a', role_id='a', performer_id='voice-a', canon={'name': '阿青'}, profile={})]


class ScriptedGenerator:
    def directions(self, s):
        return {'directions': [dict(title=str(i), premise='相遇') for i in range(3)]}

    def outline(self, s):
        return dict(title='故事', premise='相遇之后', relationships=['朋友'], series_arc='同行', duration_sec=90,
            episode_summaries=['一集'] * (s['creation']['series_episodes'] if s['creation']['form'] == 'series' else 1),
            character_portrayals=[dict(role_id='a')], scenes=[dict(title=str(i), location='竹林', time_of_day='白天',
                environment='竹林微风', atmosphere='温暖', goal='找到线索', beats=['寻找'], background_prompt='竹林',
                must_include=[], must_avoid=[], choices=[]) for i in range(3)])

    def scene(self, s, i):
        return {'scene': {'scene_id': s['scene_keys'][i], 'text': str(i)},
                'continuity': {'facts': ['线索'], 'open_threads': []}, 'preview_blurb': '相遇与寻找'}

    def finalize(self, s):
        return {'story_version_id': 'v-' + str(s['generation_epoch']), 'episodes': [{'episode_summary': '完成'}], 'continuity_state': {}}


@pytest.fixture
def env(tmp_path):
    store = Store(create_engine('sqlite:///' + str(tmp_path / 'sessions.db')))
    store.migrate()
    service = Service(store)
    media = []
    worker = Worker(service, ScriptedGenerator, lambda s, key: media.append(key) or {'job_id': key})
    state = service.create('owner', Creation(idempotency_key='creation-1', character_ids=['a'], method='idea', idea='相遇', output='audio'), CHARS)
    return service, worker, state['id'], media


def cmd(env, kind, **kwargs):
    svc, _, sid, _ = env
    s = svc.store.get(sid, 'owner')
    return svc.command(sid, 'owner', Command(command_id=kind + '-' + str(s['revision']),
        expected_revision=s['revision'], kind=kind, **kwargs))


def start(env):
    svc, w, sid, _ = env
    assert w.run_once()
    s = svc.store.get(sid, 'owner')
    cmd(env, 'confirm_outline', target_id=s['plan_id'], fingerprint=s['outline_fingerprint'])


def finish(env):
    for _ in range(5):
        env[1].run_once()


def test_confirmation_gate_and_restart(env):
    start(env)
    finish(env)
    svc, w, sid, media = env
    s = svc.store.get(sid, 'owner')
    assert s['stage'] == 'script_ready' and not media
    cmd(env, 'confirm_script', target_id=s['delivery']['story_version_id'], fingerprint=s['script_fingerprint'])
    Worker(Service(Store(svc.store.engine)), ScriptedGenerator, w.media).run_once()
    assert len(media) == 1
    assert not w.run_once()


def test_idempotency_and_owner(env):
    svc, _, sid, _ = env
    c = Command(command_id='cancel-unique', expected_revision=1, kind='cancel')
    first = svc.command(sid, 'owner', c)
    assert svc.command(sid, 'owner', c)['receipt'] == first['receipt']
    with pytest.raises(KeyError):
        svc.command(sid, 'other', c)
    with pytest.raises(Conflict):
        svc.command(sid, 'owner', c.model_copy(update={'kind': 'retry'}))


def test_pending_change_preserves_prefix(env):
    svc, w, sid, _ = env
    start(env)
    w.run_once()
    before = svc.store.get(sid, 'owner')
    cmd(env, 'change', target_id=before['scene_keys'][1], option_id='warmer')
    w.run_once()
    s = svc.store.get(sid, 'owner')
    assert s['stage'] == 'change_ready'
    cmd(env, 'confirm_change', fingerprint=fingerprint(s['pending_change']))
    w.run_once()
    s = svc.store.get(sid, 'owner')
    assert s['scenes'] == before['scenes']
    assert s['generation_epoch'] == 2
    assert s['stage'] == 'outline_ready'


def test_change_during_model_call(env):
    svc, w, sid, _ = env
    start(env)
    class Changing(ScriptedGenerator):
        def scene(self, s, i):
            cmd(env, 'change', target_id=s['scene_keys'][0], text='改变结尾')
            return super().scene(s, i)
    Worker(svc, Changing).run_once()
    assert svc.store.get(sid, 'owner')['stage'] == 'change_ready'


def test_cancel_fences_late_result(env):
    svc, w, sid, _ = env
    class Cancel(ScriptedGenerator):
        def outline(self, s):
            cmd(env, 'cancel')
            return super().outline(s)
    Worker(svc, Cancel).run_once()
    s = svc.store.get(sid, 'owner')
    assert s['stage'] == 'cancelled' and s['outline'] is None


def test_concurrent_confirmation_only_one_wins(env):
    svc, w, sid, _ = env
    w.run_once()
    s = svc.store.get(sid, 'owner')
    def confirm(i):
        try:
            svc.command(sid, 'owner', Command(command_id='confirmation-' + str(i), expected_revision=s['revision'],
                kind='confirm_outline', target_id=s['plan_id'], fingerprint=s['outline_fingerprint']))
            return True
        except Conflict:
            return False
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(confirm, range(2))).count(True) == 1


def test_background_disabled_not_fake_success(env):
    start(env)
    s = env[0].store.get(env[2], 'owner')
    assert all(b['status'] == 'disabled' for b in s['backgrounds'].values())


def test_revision_rejects_old_script(env):
    start(env)
    finish(env)
    s = env[0].store.get(env[2], 'owner')
    cmd(env, 'change', target_id=s['scene_keys'][0], option_id='warmer')
    with pytest.raises(Conflict):
        cmd(env, 'confirm_script', target_id=s['delivery']['story_version_id'], fingerprint=s['script_fingerprint'])


def test_event_sequence_survives_restart(env):
    start(env)
    finish(env)
    svc, _, sid, _ = env
    s = Store(svc.store.engine).get(sid, 'owner')
    assert [e['seq'] for e in s['events']] == list(range(1, s['last_seq'] + 1))


def test_unknown_provider_result_is_not_offered_as_retry(env):
    from drama_engine.interactive.store import public
    class Provider:
        call_history=[]
        def complete(self,*args,**kwargs):raise OSError('transport disconnected')
    class Lost:
        def __init__(self):self.provider=Provider()
        def outline(self,state):self.provider.complete(type('Spec',(),{'role':'outline'})(),'system','user')
    service,_,sid,_=env
    Worker(service,Lost).run_once()
    state=service.store.get(sid,'owner')
    assert state['error_code']=='EXTERNAL_RESULT_UNKNOWN'
    assert 'retry' not in public(state)['available_actions']


def test_short_and_series_choice_only(tmp_path):
    store = Store(create_engine('sqlite:///' + str(tmp_path / 's.db')))
    store.migrate()
    svc = Service(store)
    s = svc.create('o', Creation(idempotency_key='series-key', character_ids=['a'], form='series'), CHARS)
    w = Worker(svc, ScriptedGenerator)
    w.run_once()
    state = store.get(s['id'], 'o')
    svc.command(s['id'], 'o', Command(command_id='select-key', expected_revision=state['revision'],
        kind='select_direction', target_id=state['directions'][0]['id']))
    w.run_once()
    assert len(store.get(s['id'], 'o')['outline']['episode_summaries']) == 6


def test_preferences_replan_and_reject_stale_approval(env):
    svc, w, sid, _ = env
    w.run_once()
    before = svc.store.get(sid, 'owner')
    cmd(env, 'set_preferences', ending='open', focus_role_id='a')
    with pytest.raises(Conflict):
        cmd(env, 'confirm_outline', target_id=before['plan_id'], fingerprint=before['outline_fingerprint'])
    w.run_once()
    after = svc.store.get(sid, 'owner')
    assert after['creation']['ending'] == 'open'
    assert after['generation_epoch'] == before['generation_epoch'] + 1
    assert after['plan_id'] != before['plan_id']
    assert 'a' in after['feedback'][-1]
    cmd(env, 'confirm_outline', target_id=after['plan_id'], fingerprint=after['outline_fingerprint'])
    with pytest.raises(Conflict):
        cmd(env, 'set_preferences', ending='happy')


def test_series_episode_count_changes_before_approval(env):
    svc, w, _, _ = env
    created = svc.create('owner', Creation(idempotency_key='series-count', character_ids=['a'],
        form='series', method='idea', idea='寻找', output='script'), CHARS)
    sid = created['id']
    w.run_once()  # the older fixture session
    w.run_once()
    s = svc.store.get(sid, 'owner')
    svc.command(sid, 'owner', Command(command_id='count-change', expected_revision=s['revision'],
        kind='set_preferences', series_episodes=3))
    w.run_once()
    assert len(svc.store.get(sid, 'owner')['outline']['episode_summaries']) == 3
    assert len(svc.store.get(sid, 'owner')['series_outline']['episode_summaries']) == 3


def test_story_only_never_dispatches_media_or_legacy_work(env):
    svc, _, sid, media = env
    svc.story_only = True
    with pytest.raises(Conflict, match='STORY_ONLY_OUTPUT_REQUIRED'):
        svc.create('owner', Creation(idempotency_key='reject-audio', character_ids=['a'], output='audio'), CHARS)
    worker = Worker(svc, ScriptedGenerator, lambda *args: media.append('unexpected'))
    assert not worker.run_once()  # preexisting audio session remains untouched
    assert svc.store.get(sid, 'owner')['stage'] == 'outlining'
    created = svc.create('owner', Creation(idempotency_key='script-only', character_ids=['a'],
        method='idea', idea='寻找', output='script'), CHARS)
    story_env = svc, worker, created['id'], media
    start(story_env)
    finish(story_env)
    s = svc.store.get(created['id'], 'owner')
    cmd(story_env, 'confirm_script', target_id=s['delivery']['story_version_id'], fingerprint=s['script_fingerprint'])
    assert svc.store.get(created['id'], 'owner')['stage'] == 'confirmed'
    assert not worker.run_once()
    assert media == []


def test_single_scene_change_preserves_both_sides_and_confirmed_history(env):
    svc, w, sid, _ = env
    start(env)
    finish(env)
    before = svc.store.get(sid, 'owner')
    cmd(env, 'confirm_script', target_id=before['delivery']['story_version_id'], fingerprint=before['script_fingerprint'])
    # Legacy media dispatch is irrelevant here: emulate the confirmed-only terminal state.
    svc.store.mutate(sid, 'owner', lambda s: s.update(stage='confirmed'))
    cmd(env, 'change', target_id=before['scene_keys'][1], scope='scene', option_id='interaction')
    pending = svc.store.get(sid, 'owner')['pending_change']
    assert pending['start'] == 1 and pending['scope'] == 'scene'
    cmd(env, 'confirm_change', fingerprint=fingerprint(pending))
    assert w.run_once()
    replanned = svc.store.get(sid, 'owner')
    cmd(env, 'confirm_outline', target_id=replanned['plan_id'], fingerprint=replanned['outline_fingerprint'])
    finish(env)
    after = svc.store.get(sid, 'owner')
    assert after['scenes'][0] == before['scenes'][0]
    assert after['scenes'][2] == before['scenes'][2]
    assert after['version_history'][0]['delivery'] == before['delivery']
    assert after['delivery']['story_version_id'] != before['delivery']['story_version_id']
    assert after['stage'] == 'script_ready'
