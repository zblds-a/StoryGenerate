"""Retry one rejected real Remix with the unchanged approval, retaining attempt1."""
import sys,json,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/acceptance'))
import real_operations_chain as a
out=Path(__file__).resolve().parent
label='round_1_remix'; original=out/label; archived=out/'attempts'/(label+'_attempt1')
# Resolve and validate all paths sequentially on Windows before moving.
assert original.resolve().is_relative_to(out.resolve())
assert archived.resolve().is_relative_to(out.resolve())
request=json.loads((original/'request.json').read_text(encoding='utf-8'))
job=json.loads((original/'failed_job.json').read_text(encoding='utf-8'))
archived.parent.mkdir(exist_ok=True); original.rename(archived)
manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
engine=a.engine_for_schema('postgresql+psycopg://storygen:storygen_dev@localhost:5432/storygenerate',manifest['schema'])
start=time.monotonic()
a.run_operation(engine,out,label,request,retry_job_id=job['job_id'])
engine.dispose()
a.save(out/'retry_manifest.json',{'implementation_sha':manifest['git_sha'],'approved_snapshot_reused':True,'started_from_job_id':job['job_id'],'completed_at':datetime.now(timezone.utc).isoformat(),'wall_time_sec':time.monotonic()-start})
