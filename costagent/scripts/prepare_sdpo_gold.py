"""Extract privileged reference patches only for explicitly selected training tasks."""
import json
from pathlib import Path
import pyarrow.parquet as pq
root=Path(__file__).resolve().parents[2];batch=root/'costagent/artifacts/mixed-temperature-v1'
plan=json.loads((batch/'plan.json').read_text());allowed={r['task_id'] for r in plan['tasks']}
gold={}
for line in (root/'data/tasks.jsonl').read_text().splitlines():
 row=json.loads(line)
 if row['instance_id'] in allowed:gold[row['instance_id']]=row['patch']
for b in pq.ParquetFile(root/'swe-rebench-work/metadata/train.parquet').iter_batches(columns=['instance_id','patch']):
 for row in b.to_pylist():
  if row['instance_id'] in allowed:gold[row['instance_id']]=row['patch']
(batch/'training_tasks.json').write_text(json.dumps(sorted(allowed),indent=2)+'\n')
(batch/'teacher_only_gold.json').write_text(json.dumps(gold,indent=2)+'\n')
print('Training-only reference patches:',len(gold))
