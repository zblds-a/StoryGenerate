import json
from io import BytesIO
from contextlib import contextmanager
import pytest
from sqlalchemy import create_engine
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from drama_engine.interactive.api import register_routes
from drama_engine.interactive.service import Service, Worker
from drama_engine.interactive.store import Store
from drama_engine.interactive.models import Creation, Command
from drama_engine.interactive.generator import Generator, SceneResult
from drama_engine.interactive.streaming import StreamingProvider
from drama_engine.llm.openai_compat import OpenAICompatProvider
from drama_engine.llm.router import resolve_spec
from test_interactive_sessions import ScriptedGenerator, CHARS


@pytest.fixture
def service(tmp_path):
    store = Store(create_engine('sqlite:///' + str(tmp_path/'s.db')))
    store.migrate()
    return Service(store)


def test_authenticated_poll_and_conflicts(service, tmp_path):
    app = FastAPI()
    def owner(req):
        token = req.headers.get('authorization')
        if not token:
            raise HTTPException(401)
        return token
    register_routes(app, service, owner, lambda o, ids: CHARS, tmp_path)
    with TestClient(app) as c:
        assert c.get('/api/v1/story-options').status_code == 401
        headers={'Authorization':'owner'}
        payload={'idempotency_key':'api-creation', 'character_ids':['a']}
        first=c.post('/api/v1/story-sessions',json=payload,headers=headers).json()['data']
        again=c.post('/api/v1/story-sessions',json=payload,headers=headers).json()['data']
        assert first['id']==again['id']
        prefix='/api/v1/story-sessions/'+first['id']
        assert c.get(prefix,headers={'Authorization':'other'}).status_code==404
        assert c.get('/api/v1/story-sessions',headers={'Authorization':'other'}).json()['data']['items']==[]
        batch=c.get(prefix+'/events?poll=true&after=0',headers=headers).json()['data']
        assert [e['seq'] for e in batch['events']]==[1]
        assert c.get(prefix+'/events?poll=true&after=1',headers=headers).json()['data']['events']==[]
        assert c.get(prefix+'/events?after=100',headers=headers).status_code==409
        assert c.post(prefix+'/commands',headers=headers,json={'command_id':'stale-cancel', 'kind':'cancel','expected_revision':99}).status_code==409


def test_real_generator_creates_valid_delivery(service):
    s=service.create('o',Creation(idempotency_key='generator-key',character_ids=['a'],method='idea',idea='寻找'),CHARS)
    raw=service.store.get(s['id'],'o')
    raw.update(outline=ScriptedGenerator().outline(raw), scene_keys=['s1','s2','s3'])
    # Model test double exercises production parsing, cast routing, performance and delivery checks.
    class Provider:
        def complete_structured(self,spec,system,user,schema):
            if issubclass(schema, SceneResult):
                return schema.model_validate({'scene':{'title':'寻找','location':'竹林','dramatic_goal':'寻找',
                    'lines':[{'kind':'dialogue','speaker_role_id':'a','text':'我们一起寻找新的线索。'*10}]},
                    'facts':['发现线索'],'open_threads':[],'preview_blurb':'两个伙伴在竹林中寻找遗失的物件，听见意外的声音。'})
            data=json.loads(user)
            return schema.model_validate({'annotations':[{'line_id':line['line_id'],'emotion':'neutral',
                'tone_instruction':'自然温和','emphasis':[{'span_text':'线索','occurrence':1}],
                'speech_rate':1.0} for line in data['spoken_lines']]})
    generator=Generator(Provider())
    raw['outline']['character_portrayals']=[{'role_id':'a','story_name':'阿青','external_goal':'寻找',
        'emotional_avoidance':'怕失去朋友','speech_style':'温柔','relationship_stance':'信任'}]
    for i in range(3):raw['scenes'].append(generator.scene(raw,i))
    delivery=generator.finalize(raw)
    assert delivery['status']=='READY'
    assert delivery['quality_report']['outline_alignment_passed'] is False
    assert all(u['performer_id']=='voice-a' for sc in delivery['episodes'][0]['scenes'] for u in sc['utterances'])


def test_stream_only_whitelisted_complete_strings(monkeypatch):
    provider=OpenAICompatProvider('test-key')
    seen=[]
    chunks=['{"title":"竹', '林","reasoning":"private","text":"发现线索"}']
    class Response:
        headers={}
        def raise_for_status(self):pass
        def iter_lines(self):
            for text in chunks:
                yield 'data: '+json.dumps({'choices':[{'delta':{'content':text,'reasoning_content':'secret'}}]})
            yield 'data: '+json.dumps({'choices':[], 'usage':{'prompt_tokens':12,'completion_tokens':9}})
            yield 'data: [DONE]'
    @contextmanager
    def stream(*a,**kw):yield Response()
    monkeypatch.setattr('drama_engine.interactive.streaming.httpx.stream',stream)
    result=StreamingProvider(provider,lambda *v:seen.append(v),True).complete(resolve_spec('outline'),'system','user')
    assert json.loads(result.text)['title']=='竹林'
    assert [v[2] for v in seen]==['竹林','发现线索']
    assert provider.call_history[0]['usage_source']=='reported'


def test_stream_disconnect_never_replays(monkeypatch):
    calls=[]
    @contextmanager
    def stream(*a,**kw):
        calls.append(1)
        raise OSError('broken')
        yield
    monkeypatch.setattr('drama_engine.interactive.streaming.httpx.stream',stream)
    provider=OpenAICompatProvider('test-key')
    with pytest.raises(OSError):
        StreamingProvider(provider,lambda *v:None,True).complete(resolve_spec('outline'),'system','user')
    assert len(calls)==1 and provider.call_history[0]['usage_source']=='unavailable'


def test_writer_schema_rejects_unapproved_voice_before_annotation():
    from pydantic import ValidationError
    from drama_engine.interactive.generator import bound_scene_schema
    schema=bound_scene_schema({'qing','mo'})
    payload={'scene':{'title':'归还','location':'修理铺','dramatic_goal':'承认错误','lines':[
        {'kind':'dialogue','speaker_role_id':'shopkeeper','text':'你们来了。'}]},
        'facts':[],'open_threads':[],'preview_blurb':'两个伙伴鼓起勇气，准备归还修好的物件。'}
    with pytest.raises(ValidationError):schema.model_validate(payload)
    payload['scene']['lines'][0]['speaker_role_id']=None
    with pytest.raises(ValidationError):schema.model_validate(payload)
    payload['scene']['lines'][0]['speaker_role_id']='qing'
    assert schema.model_validate(payload).scene.lines[0].speaker_role_id=='qing'


def test_short_outline_contract_does_not_request_six_episodes(service):
    from pydantic import ValidationError
    raw=service.create('o',Creation(idempotency_key='outline-count',character_ids=['a'],method='idea',idea='相遇'),CHARS)
    state=service.store.get(raw['id'],'o')
    class Inspect:
        def complete_structured(self,spec,system,user,schema):
            data=json.loads(user)
            assert 'series_episodes' not in data['creation']
            assert data['episode_count_required']==1
            payload=ScriptedGenerator().outline(state)
            payload['character_portrayals']=[dict(role_id='a',story_name='阿青',external_goal='寻找',
                emotional_avoidance='怕失去朋友',speech_style='温柔',relationship_stance='信任')]
            payload['episode_summaries']=['故事']*6
            with pytest.raises(ValidationError):schema.model_validate(payload)
            payload['episode_summaries']=['故事']
            return schema.model_validate(payload)
    assert len(Generator(Inspect()).outline(state)['episode_summaries'])==1


def test_length_repair_cannot_change_a_protected_suffix():
    state={'outline':{'duration_sec':90},'change_scope':'scene','change_start':0,
           'scenes':[{'scene':{'utterances':[{'kind':'dialogue','text':'长'*500}]}}]*3}
    with pytest.raises(ValueError,match='EPISODE_DURATION_OUT_OF_RANGE'):
        Generator(None).finalize(state)


def test_background_image_is_16_9_and_cached(service,tmp_path):
    Image=pytest.importorskip('PIL.Image')
    from drama_engine.interactive.backgrounds import BackgroundWorker
    s=service.create('o',Creation(idempotency_key='images-key',character_ids=['a'],method='idea',idea='竹林'),CHARS)
    service.images_enabled=True
    worker=Worker(service,ScriptedGenerator)
    worker.run_once()
    raw=service.store.get(s['id'],'o')
    service.command(s['id'],'o',Command(command_id='image-confirm',expected_revision=raw['revision'],kind='confirm_outline',
        target_id=raw['plan_id'],fingerprint=raw['outline_fingerprint']))
    calls=[]
    class Images:
        def generate(self,spec):
            calls.append(1)
            img=Image.new('RGB',(400,300));out=BytesIO();img.save(out,format='PNG')
            return out.getvalue(),'test-image-model'
    images=BackgroundWorker(service,Images(),tmp_path/'images')
    for _ in range(3):assert images.run_once()
    result=service.store.get(s['id'],'o')
    assert all(bg['image']['size']==[1536,864] for bg in result['backgrounds'].values())
    assert len(calls)==1


def test_adjustment_while_finalizing_does_not_publish(service):
    s=service.create('o',Creation(idempotency_key='late-change',character_ids=['a'],method='idea',idea='竹林'),CHARS)
    worker=Worker(service,ScriptedGenerator)
    worker.run_once();raw=service.store.get(s['id'],'o')
    service.command(s['id'],'o',Command(command_id='confirm-late',expected_revision=raw['revision'],kind='confirm_outline',target_id=raw['plan_id'],fingerprint=raw['outline_fingerprint']))
    for _ in range(3):worker.run_once()
    class Late(ScriptedGenerator):
        def finalize(self,state):
            raw=service.store.get(s['id'],'o')
            service.command(s['id'],'o',Command(command_id='change-late',expected_revision=raw['revision'],kind='change',text='改变结尾'))
            return super().finalize(state)
    Worker(service,Late).run_once()
    state=service.store.get(s['id'],'o')
    assert state['stage']=='change_ready' and state['delivery'] is None
