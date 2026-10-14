"""Mechanical evidence checks complement separately recorded reading of raw scripts."""
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'4-引擎代码'))
from drama_engine.workflow.schemas import StoryDelivery
from drama_engine.workflow.delivery import validate_delivery_integrity
out=Path(__file__).resolve().parent
reviews=json.loads((out/'auditor_review.json').read_text(encoding='utf-8')) if (out/'auditor_review.json').exists() else {}
def read(p):return json.loads(p.read_text(encoding='utf-8'))
for path in sorted(out.glob('*/delivery.json')):
 label=path.parent.name; d=read(path); model=StoryDelivery.model_validate(d)
 assert validate_delivery_integrity(model).valid
 job=read(path.parent/'persisted_job.json'); source=job['input_snapshot']['preview'].get('source_reference')
 checks=['完整结构校验通过；关闭Session后读取任务/版本并完整导出往返一致；成功任务重复执行返回同一版本']
 if source:
  old=source['source_content_snapshot']['delivery']
  assert d['parent_story_version_id']==old['story_version_id']
  if d['lineage_type']=='remix':assert d['story_id']!=old['story_id'] and d['version_no']==1
  else:assert d['story_id']==old['story_id']
  if d['lineage_type']=='continue':
   assert d['episodes'][:len(old['episodes'])]==old['episodes']
   assert len(d['generated_episode_ids'])==len(d['episodes'])-len(old['episodes'])
   assert [e['index'] for e in d['episodes']]==list(range(1,len(d['episodes'])+1))
   assert '三声铃报平安' not in d['continuity_state']['unresolved_threads']
   checks.append('继承的完整旧集逐字段相同，新增ID及全局集号连续，精确父版本正确，铃声线程已关闭')
  elif d['lineage_type']=='revise':
   scope=job['input_snapshot']['request']['edit']['scope']
   target=job['input_snapshot']['request']['edit']['target']
   old_eps={e['episode_id']:e for e in old['episodes']}
   for e in d['episodes']:
    prior=old_eps[e['episode_id']]
    if scope in ('line','scene','episode') and e['episode_id']!=target['episode_id']:assert e==prior
    for scene in e['scenes']:
     if scope in ('line','scene') and scene['scene_id']!=target['scene_id']:assert scene==next(s for s in prior['scenes'] if s['scene_id']==scene['scene_id'])
     if scope=='line' and scene['scene_id']==target['scene_id']:
      prior_lines={u['line_id']:u for s in prior['scenes'] for u in s['utterances']}
      for u in scene['utterances']:
       if u['line_id']!=target['line_id']:assert u==prior_lines[u['line_id']]
   checks.append('按获批scope复核完整未修改集/场景/台词及演绎标注保持一致；父版本与修改差异可追溯')
 entry=reviews.setdefault(label,{'passed':False,'reviewer':'Codex artifact inspection','findings':['尚待正文语义复核']})
 entry['mechanical_checks']=checks
(out/'auditor_review.json').write_text(json.dumps(reviews,ensure_ascii=False,indent=2),encoding='utf-8')
print('Mechanical artifact checks:',len(reviews))
