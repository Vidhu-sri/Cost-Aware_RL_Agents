"""Build a review-aware batch index without editing any raw attempt result."""
import json,sys
from collections import Counter
from pathlib import Path

def main(batch):
    raw=json.loads((batch/'manifest.json').read_text())
    records=[]
    for entry in raw['attempts']:
        record=dict(entry)
        path=Path(entry['result_dir'])
        review=path/'classification_review.json'
        if review.exists():
            correction=json.loads(review.read_text())
            record.update({k:correction[k] for k in ('category','resolved','reward')})
            record['classification_review']=str(review)
            record['classification_reason']=correction['reason']
        records.append(record)
    counts=Counter(r['category'] for r in records)
    output={'source_manifest':str(batch/'manifest.json'),'completed_attempts':len(records),
            'distinct_tasks':len(set(r['task_id'] for r in records)),
            'counts':dict(counts),'tasks':raw['tasks'],'attempts':records,
            'setup_failures':raw['setup_failures'],'integration_setup_failures':raw.get('integration_setup_failures',[]),
            'stop_reason':raw.get('stop_reason'),'server_cleanup':raw.get('server_cleanup')}
    path=batch/'effective_manifest.json';temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(output,indent=2)+'\n');temp.replace(path)
    print(json.dumps({'completed_attempts':output['completed_attempts'],'counts':output['counts'],'tasks':output['distinct_tasks']}))
if __name__=='__main__':main(Path(sys.argv[1]).resolve())
