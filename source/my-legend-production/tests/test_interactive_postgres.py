"""Real isolated PostgreSQL handoff, without providers or synthetic successful audio."""
from copy import deepcopy
import pytest
from test_production_queue import env
from test_interactive_bridge import delivery
from drama_engine.interactive.models import Creation, Command, fingerprint
from drama_engine.interactive.service import Worker
from my_legend_production.production.interactive import session_service, media_submit
from my_legend_production.production.flows import FlowService
from my_legend_production.production.story import StoryStage
from my_legend_production.production.worker import ProductionWorker
from my_legend_production.production.contracts import ProductionRequest
from my_legend_production.production.repository import ProductionError


def test_confirmed_session_handoff_owner_and_no_duplicate_production(env, delivery):
    repo, artifacts = env
    service = session_service(repo)
    service.store.migrate()
    chars = [dict(character_id='a',role_id='a',performer_id='performer-a',canon={'name':'阿青'},profile={})]
    session = service.create('alice', Creation(idempotency_key='postgres-session',character_ids=['a'],method='idea',idea='合作'),chars)
    sid = session['id']
    def ready(s):
        s.update(stage='script_ready',delivery=delivery,script_fingerprint=fingerprint(delivery))
    service.store.mutate(sid,'alice',ready)
    assert repo.list_jobs('alice')['items'] == []
    raw = service.store.get(sid,'alice')
    command = Command(command_id='postgres-confirm',expected_revision=raw['revision'],kind='confirm_script',
        target_id=delivery['story_version_id'],fingerprint=fingerprint(delivery))
    service.command(sid,'alice',command)
    worker = Worker(service, lambda: None, media_submit(repo, artifacts))
    assert worker.run_once()
    receipt = service.command(sid,'alice',command)
    assert receipt['session']['stage'] == 'media_ready'
    assert not worker.run_once()
    flows = FlowService(repo,artifacts)
    assert len(flows.listing('alice')['items']) == 1
    fid = service.store.get(sid,'alice')['media']['flow_id']
    flows.advance(fid,'alice')
    sound = flows.jobs(flows.row(fid,'alice'))['sound']
    assert sound['request']['source']['source_version_id'] == delivery['story_version_id']
    foreign = deepcopy(sound['request']);foreign['idempotency_key']='foreign-session-source'
    with pytest.raises(ProductionError,match='SOURCE_ARTIFACT_NOT_OWNED'):
        repo.create('bob',ProductionRequest.model_validate(foreign))
    # Consume the actual immutable handoff; no remote story service may be called.
    assert ProductionWorker(repo,artifacts,{'story':StoryStage(None)},only_configured_stages=True).tick()
    result = repo.get(sound['id'],'alice')
    assert next(s for s in result['stages'] if s['name']=='story')['status'] == 'succeeded'
    assert result['actual_calls'] == 0
    service.store.engine.dispose()
