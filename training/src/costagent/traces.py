"""Read the observed ATIF-v1.7 format and authoritative batch indexes."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[3]
TRAIN = ROOT / 'swe-rebench-work/results/gemma100-v2-20261021/effective_manifest.json'
EVAL = ROOT / 'baseline-kit/results/docker-gemma129-20261017b-agent-batch/all129_per_task.json'
ARTIFACTS = ROOT / 'artifacts'


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, data):
    path = Path(path).resolve()
    allowed_roots = [ARTIFACTS.resolve()]
    if os.environ.get('GEMMA_DPO_OUTPUT_ROOT'):
        allowed_roots.append(Path(os.environ['GEMMA_DPO_OUTPUT_ROOT']).resolve())
    if not any(path.is_relative_to(root) for root in allowed_roots):
        raise ValueError('Derived output must be under artifacts/ or the explicit GEMMA_DPO_OUTPUT_ROOT')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def load_trace(path):
    data = read_json(path)
    if data.get('schema_version') != 'ATIF-v1.7':
        raise ValueError(f'Unsupported trace schema: {path}')
    for step in data['steps']:
        if step['source'] not in {'agent', 'user', 'system'}:
            raise ValueError(f'Unknown source in {path}')
        for call in step.get('tool_calls', []):
            if not isinstance(call['arguments'], dict):
                raise ValueError(f'Non-object tool arguments in {path}')
    return data


def load_run(index, source):
    """Use explicit indexes: never mix exploratory, reference or retry directories."""
    if source not in {'swe_rebench', 'kaggle_dev'}:
        raise ValueError(source)
    data = read_json(index)
    entries = data['attempts'] if source == 'swe_rebench' else data
    records = []
    for entry in entries:
        directory = Path(entry['result_dir'])
        trace_path = directory / 'trace.json' if source == 'swe_rebench' else Path(entry['trace_path'])
        trace = load_trace(trace_path)
        solved = entry['resolved'] if source == 'swe_rebench' else entry['agent_resolved']
        if solved is not None and type(solved) is not bool:
            raise ValueError('Solve label must be boolean or unknown')
        requests_path = directory / 'model_requests.jsonl'
        requests = [json.loads(line) for line in requests_path.open()] if requests_path.exists() else []
        records.append(dict(task_id=entry['task_id'], rollout_id=str(directory), source=source,
                            solved=solved, category=entry.get('category', entry.get('verification_status')),
                            steps=trace['steps'], final_metrics=trace['final_metrics'], requests=requests,
                            trace_path=str(trace_path), seed=entry.get('seed'),
                            wall_s=entry.get('agent', {}).get('elapsed_seconds'),
                            base_commit=(read_json(directory / 'safe_task_input.json').get('base_commit')
                                         if (directory / 'safe_task_input.json').exists() else None)))
    if len({r['rollout_id'] for r in records}) != len(records):
        raise ValueError('Duplicate rollout in index')
    return records


def assert_train(records, allowed_tasks):
    for record in records:
        if record['source'] != 'swe_rebench' or record['task_id'] not in allowed_tasks:
            raise ValueError(f'Eval/unknown task rejected: {record["task_id"]}')


def report(records):
    calls, tokens = [], []
    for row in records:
        calls.append(sum(c['function_name'] not in {'submit_patch', 'get_status'}
                         for s in row['steps'] for c in s.get('tool_calls', [])))
        tokens.append(row['final_metrics']['total_completion_tokens'])
    group_sizes = list(Counter(r['task_id'] for r in records).values())
    known = [r for r in records if r['solved'] is not None]
    events = Counter(s.get('extra', {}).get('event_type', '') for r in records for s in r['steps'])
    return dict(tasks=len(group_sizes), rollouts=len(records),
                rollouts_per_task=[min(group_sizes), median(group_sizes), max(group_sizes)],
                solved=sum(r['solved'] is True for r in records), labeled=len(known),
                unknown_labels=len(records)-len(known),
                solve_rate_labeled=sum(r['solved'] for r in known)/len(known) if known else None,
                median_calls=median(calls), median_generated_tokens=median(tokens),
                model_request_logs=sum(bool(r['requests']) for r in records), events=dict(events),
                step_fields=sorted({k for r in records for s in r['steps'] for k in s}),
                metric_fields=sorted({k for r in records for s in r['steps'] for k in (s.get('metrics') or {})}))


def main():
    p = argparse.ArgumentParser(); p.add_argument('--train-index', type=Path, default=TRAIN)
    p.add_argument('--eval-index', type=Path, default=EVAL); args = p.parse_args()
    summaries = {}
    rows, steps = [], []
    for source, index in [('swe_rebench', args.train_index), ('kaggle_dev', args.eval_index)]:
        records = load_run(index, source); summaries[source] = report(records)
        for r in records:
            rows.append({k: v for k, v in r.items() if k not in {'steps', 'requests', 'final_metrics'}})
            steps.extend(dict(task_id=r['task_id'], rollout_id=r['rollout_id'], source=source,
                              step_json=json.dumps(s)) for s in r['steps'])
    write_json(ARTIFACTS / 'rollout_summary.json', summaries)
    import pyarrow as pa
    import pyarrow.parquet as pq
    pq.write_table(pa.Table.from_pylist(rows), ARTIFACTS / 'trajectories.parquet')
    pq.write_table(pa.Table.from_pylist(steps), ARTIFACTS / 'steps.parquet')
    text = '# Rollout inspection\n\n' + '\n\n'.join('## '+s+'\n\n```json\n'+json.dumps(v,indent=2)+'\n```' for s,v in summaries.items())
    text += '''

Counts use the SWE effective manifest (classification reviews applied) and the final
129-task Kaggle index, not recursive discovery of exploratory runs. Unknown grading
labels remain unknown and cannot enter training. Attempts include infrastructure retries;
they are not a prospectively sampled GRPO group.

Both sources use ATIF-v1.7. Per-turn prompt/completion usage and thoughts are logged.
Observation and thought token counts, logprobs, raw generated token IDs, rendered model
prompts and finish_reason are not in ATIF. Generated-token medians above exclude
observations; total cost tokens cannot be reported exactly from these traces alone.
Compaction event counts are shown above. SWE model_requests.jsonl logs exact API request
messages, tools and template kwargs, including compacted contexts. Requests can include
retries and summarizer calls; positional zipping with ATIF steps is invalid. Subsequent
requests retain structured assistant messages, but these do not prove exact generated
serialization or recover terminal responses. Kaggle logs must not be used for training.

Gold source patches are present in metadata/train.parquet (the patch column), distinct
from test_patch in grading_spec.json. SWE generation explicitly disables graphs. Its
base-commit source trees must be supplied before graph rewards can be built; Kaggle
snapshots/graphs are not substitutes. Existing graphs are NetworkX node-link JSON with
nodes {id,name,text}, edges {source,target,key,type}, directed=true, multigraph=true.

Most train tasks have one usable rollout; Kaggle has one per task. DPO sibling pairs
and GRPO groups need additional controlled sampling. See training/scripts/sample_more.sh.
Exact chat-template round-trip and loss masks cannot be certified from the current
logs: see QUESTIONS.md. No synthetic completions are emitted as training examples.
'''
    (ARTIFACTS / 'data_report.md').write_text(text)
    print(json.dumps(summaries, indent=2))

if __name__ == '__main__': main()
