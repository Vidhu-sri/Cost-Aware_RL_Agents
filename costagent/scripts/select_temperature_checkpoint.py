"""Select only on dev; final test outcomes never enter this decision."""
import json
from pathlib import Path
base=Path('artifacts/mixed-temperature-v1/evaluation');scores=[]
for i in range(1,6):
 epoch=f'epoch-{i:03d}';data=json.loads((base/f'{epoch}-dev-manifest.json').read_text())['attempts']
 if len(data)!=12 or any(r['resolved'] is None for r in data):raise RuntimeError(f'Incomplete development evaluation: {epoch}')
 solved=sum(r['resolved'] for r in data)
 tokens=[]
 for r in data:
  trace=json.loads(Path(r['trace_path']).read_text());tokens.append(trace['final_metrics']['total_completion_tokens'])
 scores.append(dict(epoch=epoch,solved=solved,mean_generated_tokens=sum(tokens)/len(tokens)))
best=min(scores,key=lambda r:(-r['solved'],r['mean_generated_tokens'],r['epoch']))
(base/'selection.json').write_text(json.dumps(dict(**best,candidates=scores,criterion='dev solve count descending, generated tokens ascending; no test access'),indent=2)+'\n')
