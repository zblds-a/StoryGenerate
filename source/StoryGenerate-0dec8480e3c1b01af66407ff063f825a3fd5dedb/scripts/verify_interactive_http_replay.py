"""Replay real persisted artifacts through business HTTP routes without paid calls."""
import argparse
import json
from pathlib import Path
from sqlalchemy import create_engine
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from drama_engine.interactive.store import Store
from drama_engine.interactive.service import Service
from drama_engine.interactive.api import register_routes


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--database-url',required=True)
    parser.add_argument('--session-id',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    store=Store(create_engine(args.database_url))
    service=Service(store)
    def owner(request):
        if request.headers.get('authorization')=='Bearer acceptance-fixture':return 'acceptance'
        if request.headers.get('authorization')=='Bearer other-fixture':return 'other'
        raise HTTPException(401)
    def no_create(*args):raise AssertionError('No creation or model dispatch during replay')
    app=FastAPI();register_routes(app,service,owner,no_create,args.output.parent)
    path='/api/v1/story-sessions/'+args.session_id
    headers={'Authorization':'Bearer acceptance-fixture'}
    before=store.get(args.session_id,'acceptance')
    with TestClient(app) as client:
        assert client.get(path).status_code==401
        assert client.get(path,headers={'Authorization':'Bearer other-fixture'}).status_code==404
        snapshot=client.get(path,headers=headers).json()['data']
        assert snapshot['id']==args.session_id
        assert client.get(path+'/export',headers=headers).json()['data']['delivery']==before['delivery']
        seq=0;events=[]
        while True:
            batch=client.get(path+'/events',params={'poll':True,'after':seq},headers=headers).json()['data']
            if not batch['events']:break
            events.extend(batch['events']);seq=batch['last_seq']
        assert [e['seq'] for e in events]==list(range(1,before['last_seq']+1))
        assert client.get(path+'/events',params={'after':seq+1},headers=headers).status_code==409
        assert client.post(path+'/commands',headers=headers,json={'command_id':'replay-stale-command',
            'expected_revision':1,'kind':'confirm_script','target_id':'stale','fingerprint':'x'*64}).status_code==409
    after=store.get(args.session_id,'acceptance')
    assert after['call_count']==before['call_count'] and after['last_seq']==before['last_seq']
    report={'session_id':args.session_id,'checks':['authentication','owner_isolation','snapshot',
        'export_exact_match','event_replay_no_gap_or_duplicate','cursor_conflict','stale_command_rejected','no_new_model_calls'],
        'passed':True,'paid_calls':0}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
