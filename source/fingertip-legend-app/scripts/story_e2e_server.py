"""Offline browser acceptance server. Uses real session API/store/worker and marked fixtures.
Never import this module from production. No model, image, voice or animation supplier is called.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from uuid import uuid4

ENGINE = Path(__file__).resolve().parents[2] / 'StoryGenerate-0dec8480e3c1b01af66407ff063f825a3fd5dedb'
sys.path.insert(0, str(ENGINE / '4-引擎代码'))
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from drama_engine.interactive.api import register_routes
from drama_engine.interactive.service import Service, Worker
from drama_engine.interactive.store import Store, emit

fixture=json.loads((ENGINE/'docs/examples/interactive/short-session.real-example.json').read_text(encoding='utf-8'))
chars=[dict(character_id=cid,role_id=cid,performer_id='voice-'+cid,canon={'name':name},profile={}) for cid,name in [('qing','阿青'),('mo','小墨')]]
root=Path(tempfile.mkdtemp(prefix='story-browser-'))
service=Service(Store(create_engine('sqlite:///'+str(root/'sessions.db'))),story_only=True)
service.store.migrate()
class Fixtures:
    def directions(self,s):
        time.sleep(.2)
        return {'directions':[{'title':t,'premise':'两个伙伴一起寻找遗失的录音笔。'} for t in ['竹林里的约定','夜市的回声','雨后的线索']]}
    def outline(self,s):
        time.sleep(.3)
        result=copy.deepcopy(fixture['outline'])
        result['title']='竹林里的约定'
        result['episode_summaries']=['两位伙伴寻找线索并作出选择']*(s['creation']['series_episodes'] if s['creation']['form']=='series' else 1)
        return result
    def scene(self,s,i):
        def preview(v):emit(v,'scene.text.delta',{'scene_key':s['scene_keys'][i],'attempt_id':uuid4().hex,'chunk_index':0,'text':'伙伴们正在寻找新的线索……'})
        service.store.mutate(s['id'],s['owner'],preview)
        time.sleep(2)
        result=copy.deepcopy(fixture['scenes'][i])
        result['scene']['scene_id']=s['scene_keys'][i]
        for j,line in enumerate(result['scene']['utterances']):line['line_id']=s['scene_keys'][i]+'-'+str(j)
        return result
    def finalize(self,s):
        result=copy.deepcopy(fixture['delivery'])
        result.update(story_version_id='e2e-'+uuid4().hex,story_id=s['story_id'])
        result['episodes']=[*copy.deepcopy((s.get('source_delivery') or {}).get('episodes',[])),result['episodes'][-1]]
        result['episodes'][-1].update(episode_id=s['episode_id'],index=s['episode_number'],scenes=[v['scene'] for v in s['scenes']])
        from drama_engine.workflow.schemas import StoryDelivery
        return StoryDelivery.model_validate(result).model_dump(mode='json')
app=FastAPI()
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:5193'],allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type'])
def owner(request):
    token=request.headers.get('authorization','')
    if not token.startswith('Bearer browser-'):raise HTTPException(401)
    return token
register_routes(app,service,owner,lambda o,ids:[v for v in chars if v['character_id'] in ids],root/'images')
@app.get('/health')
def health():return {'ok':True,'fixture_mode':True}
@app.get('/api/v1/characters')
def characters():return {'code':0,'message':'ok','data':[dict(id=c['character_id'],name=c['canon']['name'],description='浏览器验收测试角色',avatarUrl='',owned=True) for c in chars]}
def loop():
    worker=Worker(service,Fixtures)
    while True:
        if not worker.run_once():time.sleep(.05)
if __name__=='__main__':
    threading.Thread(target=loop,daemon=True).start()
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=5194,log_level='warning')
