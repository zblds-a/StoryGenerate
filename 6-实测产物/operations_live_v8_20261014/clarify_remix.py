"""Regenerate an ambiguous calendar after artifact review, never edit model text."""
import sys,json,time,uuid
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tests/acceptance'))
import real_operations_chain as a
out=Path(__file__).resolve().parent;original=out/'round_1_remix'
request=json.loads((original/'request.json').read_text(encoding='utf-8'))
result=json.loads((original/'result.json').read_text(encoding='utf-8'))
a.save(original/'automated_result_before_artifact_review.json',result)
result.update(status='failed',error_type='ArtifactReviewError',error='Relative fault date remains ungrounded: ep1 investigation/closure tomorrow vs ep2 apology for yesterday without explaining when the unplugging occurred. Artifact review requests an explicit same-evening timeline; automated pass is not final acceptance.')
a.save(original/'result.json',result)
archived=out/'attempts'/'round_1_remix_attempt2'
assert original.resolve().is_relative_to(out.resolve()) and archived.resolve().is_relative_to(out.resolve())
original.rename(archived)
request.update(request_id=uuid.uuid4().hex,idempotency_key=uuid.uuid4().hex)
request['user_instruction']+=' 两集均发生在同一个晚上：周野本晚制造断电并隐瞒，林岚本晚查明原因，同晚公开道歉；广播站计划在明天关停。必须交代当前断电发生在今晚，不能道歉称昨天的故障。'
request['client_context']={'operation_requirements':{'calendar':'两集均发生同一晚；本晚断电、本晚调查、本晚道歉，广播站计划明天关停。正文明确这一时间关系，不得把本晚断电写成昨天。'}}
manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'));engine=a.engine_for_schema('postgresql+psycopg://storygen:storygen_dev@localhost:5432/storygenerate',manifest['schema']);start=time.monotonic()
a.run_operation(engine,out,'round_1_remix',request)
engine.dispose()
a.save(out/'calendar_clarification_manifest.json',{'implementation_sha':manifest['git_sha'],'normal_prepare_approve_generate':True,'body_manually_edited':False,'additional_requirement':'explicit same-evening calendar','completed_at':datetime.now(timezone.utc).isoformat(),'wall_time_sec':time.monotonic()-start})
