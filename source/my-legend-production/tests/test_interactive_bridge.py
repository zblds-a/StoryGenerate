"""No providers or production DB: exercise the real confirmed-delivery handoff."""
from contextlib import contextmanager
from pathlib import Path
import json
import pytest
from my_legend_production.production.interactive import media_submit
from my_legend_production.production.artifacts import ArtifactStore
from my_legend_production.production.contracts import ProductionRequest


@pytest.fixture
def delivery():
    return json.loads((Path(__file__).resolve().parents[1] / 'examples/source/story_delivery.json').read_text(encoding='utf-8'))


def test_no_media_before_script_confirmation(delivery, tmp_path):
    with pytest.raises(ValueError, match='SCRIPT_CONFIRMATION_REQUIRED'):
        media_submit(None, ArtifactStore(tmp_path))({'confirmed_version': None, 'delivery': delivery}, 'key')
    assert list(tmp_path.iterdir()) == []


def test_confirmed_version_registers_owned_sources_and_creates_existing_flow(delivery, tmp_path, monkeypatch):
    statements, flows = [], []
    class Repo:
        @contextmanager
        def transaction(self):yield self
        def execute(self, query, parameters):statements.append((query, parameters))
    def insert(self, owner, key, original, request, casting, work_id):
        req = ProductionRequest.model_validate(request['sound'])
        assert req.source.source_version_id == delivery['story_version_id']
        assert req.source.delivery.source_version_id == req.source.manifest.source_version_id
        assert req.review_policy == 'listen_first'
        assert request['stage_mode'] == 'basic_stage/1'
        flows.append((owner, key, original, request, casting, work_id))
        return 'confirmed-flow'
    monkeypatch.setattr('my_legend_production.production.flows.FlowService.insert', insert)
    state = dict(id='session', owner='alice', story_id=delivery['story_id'],
        confirmed_version=delivery['story_version_id'], delivery=delivery, creation={'output':'audio'})
    result = media_submit(Repo(), ArtifactStore(tmp_path))(state, 'fixed-confirmed-key')
    assert result['flow_id'] == 'confirmed-flow'
    assert len(statements) == 2 and len(flows) == 1
    assert all(params[0] == 'alice' and params[2] == delivery['story_version_id'] for _, params in statements)


def test_mismatched_confirmed_version_is_rejected(delivery, tmp_path):
    with pytest.raises(ValueError, match='SCRIPT_CONFIRMATION_REQUIRED'):
        media_submit(None, ArtifactStore(tmp_path))({'confirmed_version':'different', 'delivery':delivery}, 'key')
