"""Preserve rejected evidence and retry the exact approved jobs; no content editing."""
import sys, json, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests' / 'acceptance'))
import real_operations_chain as a
out = Path(__file__).resolve().parent
manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
engine = a.engine_for_schema('postgresql+psycopg://storygen:storygen_dev@localhost:5432/storygenerate', manifest['schema'])
start = time.monotonic()
template = json.loads((out / 'round_1_remix' / 'request.json').read_text(encoding='utf-8'))
def run(n):
    label = f'round_{n}_continue'
    original = out / label
    value = json.loads((original / 'request.json').read_text(encoding='utf-8'))
    job = json.loads((original / 'failed_job.json').read_text(encoding='utf-8'))
    archived = out / 'attempts' / (label + '_attempt1')
    assert original.resolve().is_relative_to(out) and archived.resolve().is_relative_to(out)
    archived.parent.mkdir(exist_ok=True)
    original.rename(archived)
    delivery = a.run_operation(engine, out, label, value, retry_job_id=job['job_id'])
    remix_label = f'round_{n}_remix'
    blocked = out / remix_label
    archived_blocked = out / 'attempts' / (remix_label + '_blocked1')
    assert blocked.resolve().is_relative_to(out) and archived_blocked.resolve().is_relative_to(out)
    blocked.rename(archived_blocked)
    if delivery:
        extras = {k: v for k,v in template.items() if k in ('creation_preferences','remix')}
        a.run_operation(engine, out, remix_label, a.request('remix', template['user_instruction'], delivery, **extras))
    else:
        a.blocked(out, remix_label, 'remix', 'Continue retry failed')
with ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(run, (2,3)))
engine.dispose()
a.save(out / 'retry_manifest.json', {'implementation_sha': manifest['git_sha'], 'completed_at': datetime.now(timezone.utc).isoformat(), 'wall_time_sec': time.monotonic()-start, 'policy': 'one explicit retry, unchanged approved snapshot, original failures retained'})
