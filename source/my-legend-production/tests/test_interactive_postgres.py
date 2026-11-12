"""Isolated real PostgreSQL story persistence, no downstream or model calls."""
from test_production_queue import env
from test_interactive_bridge import delivery, assert_story_confirmation
from my_legend_production.production.interactive import session_service

def test_story_only_postgres_confirmation(env,delivery):
    repo,artifacts=env
    service=session_service(repo)
    sid=assert_story_confirmation(service,delivery)
    assert repo.list_jobs('alice')['items']==[]
    restarted=session_service(repo)
    assert restarted.store.get(sid,'alice')['confirmed_version']==delivery['story_version_id']
    service.store.engine.dispose()
    restarted.store.engine.dispose()


def test_enabled_business_routes_auth_export_and_no_media(env, delivery, monkeypatch):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from drama_engine.interactive.models import fingerprint
    from my_legend_production.production.interactive import register
    monkeypatch.setenv('MY_LEGEND_INTERACTIVE_STORIES', '1')
    monkeypatch.setenv('MY_LEGEND_STORY_TOKEN', 'fixture-token')
    monkeypatch.setattr('my_legend_production.production.interactive.StoryClient.call',
        lambda *args: {'version': 1, 'canon': {'name': '阿青'}, 'runtime_defaults': {}, 'assets': {}})
    repo, artifacts = env
    monkeypatch.setenv('MY_LEGEND_PRODUCTION_DSN', repo.dsn)
    monkeypatch.setenv('MY_LEGEND_PRODUCTION_RUNTIME', str(artifacts.root.parent))
    app = FastAPI()
    def owner(req):
        token = req.headers.get('authorization')
        if not token:
            raise HTTPException(401)
        return token
    register(app, repo, artifacts, owner)
    app.state.story_sessions.store.migrate()
    with TestClient(app) as client:
        assert client.get('/api/v1/story-options').status_code == 401
        headers = {'Authorization': 'alice'}
        options = client.get('/api/v1/story-options', headers=headers).json()['data']
        assert options['story_only'] and options['outputs'] == ['script']
        payload = {'idempotency_key': 'http-pg-story', 'character_ids': ['a'], 'method': 'idea', 'idea': '寻找'}
        session = client.post('/api/v1/story-sessions', headers=headers, json=payload).json()['data']
        assert session['creation']['output'] == 'script'
        path = '/api/v1/story-sessions/' + session['id']
        assert client.get(path, headers={'Authorization': 'bob'}).status_code == 404
        assert client.post('/api/v1/story-sessions', headers=headers,
            json={**payload, 'idempotency_key': 'http-no-audio', 'output': 'audio'}).status_code == 409
        app.state.story_sessions.store.mutate(session['id'], 'alice', lambda s: s.update(
            stage='script_ready', delivery=delivery, script_fingerprint=fingerprint(delivery)))
        current = client.get(path, headers=headers).json()['data']
        response = client.post(path + '/commands', headers=headers, json={
            'kind': 'confirm_script', 'command_id': 'http-pg-confirm', 'expected_revision': current['revision'],
            'target_id': delivery['story_version_id'], 'fingerprint': current['script_fingerprint']})
        assert response.status_code == 202 and response.json()['data']['session']['stage'] == 'confirmed'
        exported = client.get(path + '/export', headers=headers).json()['data']
        assert exported['confirmed'] and exported['content_fingerprint'] == fingerprint(delivery)
        events = client.get(path + '/events?poll=true&after=0', headers=headers).json()['data']
        assert client.get(path + '/events?poll=true&after=' + str(events['last_seq']), headers=headers).json()['data']['events'] == []
        assert repo.list_jobs('alice')['items'] == []
    app.state.story_sessions.store.engine.dispose()
