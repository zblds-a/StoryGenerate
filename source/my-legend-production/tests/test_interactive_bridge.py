"""Story-only integration: confirmation exports a version, never a media job."""
from pathlib import Path
import json
import pytest
from sqlalchemy import create_engine
from drama_engine.interactive.store import Store, Conflict
from drama_engine.interactive.service import Service, Worker
from drama_engine.interactive.models import Creation, Command, fingerprint

@pytest.fixture
def delivery():
    return json.loads((Path(__file__).resolve().parents[1] / 'examples/source/story_delivery.json').read_text(encoding='utf-8'))

def assert_story_confirmation(service, delivery):
    service.store.migrate()
    chars=[dict(character_id='a',role_id='a',performer_id='voice-a',canon={'name':'阿青'},profile={})]
    s=service.create('alice',Creation(idempotency_key='story-confirm',character_ids=['a'],method='idea',idea='合作',output='script'),chars)
    def ready(value):value.update(stage='script_ready',delivery=delivery,script_fingerprint=fingerprint(delivery))
    service.store.mutate(s['id'],'alice',ready)
    raw=service.store.get(s['id'],'alice')
    c=Command(command_id='confirm-once',expected_revision=raw['revision'],kind='confirm_script',target_id=delivery['story_version_id'],fingerprint=fingerprint(delivery))
    receipt=service.command(s['id'],'alice',c)
    assert receipt['session']['stage']=='confirmed'
    assert service.command(s['id'],'alice',c)['receipt']==receipt['receipt']
    calls=[]
    assert not Worker(service,lambda: calls.append('model'),lambda *args:calls.append('media')).run_once()
    assert calls==[]
    with pytest.raises(KeyError):service.store.get(s['id'],'bob')
    return s['id']

def test_story_only_confirmation(tmp_path,delivery):
    service=Service(Store(create_engine('sqlite:///'+str(tmp_path/'s.db'))),story_only=True)
    assert_story_confirmation(service,delivery)
