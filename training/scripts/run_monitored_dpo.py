#!/usr/bin/env python3
"""Five DPO epochs with sequential GPU training and fresh graded development checks."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from costagent.traces import ROOT,ARTIFACTS,write_json
from costagent.dpo_dev_eval import candidates,disk_guard
from costagent.dpo_monitor import choose_checkpoint


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ARTIFACTS/'archive-dpo-5ep')
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args();out=a.output.resolve()
    if not out.is_relative_to(ARTIFACTS.resolve()):p.error('Output must be under artifacts/')
    dataset=ARTIFACTS/'archive-dpo-v1/dataset.json'
    data=json.loads(dataset.read_text());pairs=len(data['pairs'])
    if pairs==0:raise ValueError('No training pairs')
    reference=ARTIFACTS/'resolved-sft/adapter'
    train_dir=out/'training';eval_dir=out/'evaluation';manifest=out/'dev_manifest.json'
    plan=dict(epochs=5,optimizer_steps=5*pairs,pairs=pairs,effective_batch_pairs=1,learning_rate=1e-5,
        reference=str(reference),dataset=str(dataset),context_tokens=data['report']['max_length'],
        training_tasks=data['report']['tasks'],development_tasks_per_stage=4,evaluation_stages=6,
        candidate_development_tasks=len(candidates()),minimum_free_disk_gib=20,
        held_out_final_test=False,checkpoint_selection='development solve count, then calls among solves; SFT retained on ties')
    write_json(out/'plan.json',plan);print(json.dumps(plan),flush=True)
    if a.dry_run:return
    if (out/'complete.json').exists():print('Experiment already complete');return
    harness=Path(os.environ.get('HARNESS_PYTHON','/home/mahesh/miniconda3/envs/gemma-harness/bin/python'))
    train_python=ROOT/'envs/train/bin/python';evaluations=[]
    def evaluate(stage,adapter):
        disk_guard();write_json(out/'progress.json',dict(stage='evaluation',checkpoint=stage))
        subprocess.run([str(harness),'-m','costagent.dpo_dev_eval','--adapter',str(adapter),
                        '--output',str(eval_dir/stage),'--manifest',str(manifest)],check=True,cwd=ROOT)
        summary=json.loads((eval_dir/stage/'summary.json').read_text());summary['checkpoint']=stage
        evaluations.append(summary)
        write_json(out/'comparison.json',evaluations)
        with (out/'comparison.csv').open('w',newline='') as f:
            fields=['checkpoint','tasks','solved','solve_rate','mean_calls','mean_calls_solved','adapter']
            writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(evaluations)
    evaluate('sft-baseline',reference)
    for epoch in range(1,6):
        disk_guard();write_json(out/'progress.json',dict(stage='training',epoch=epoch,total_epochs=5))
        command=[str(train_python),str(ROOT/'training/scripts/train_archive_dpo.py'),
                 '--dataset',str(dataset),'--output',str(train_dir),'--epochs','5',
                 '--through-epoch',str(epoch),'--compact-checkpoints']
        if (train_dir/'state.json').exists():command.append('--resume')
        # Completed boundaries are reusable, but cannot be skipped without their checkpoint.
        state=json.loads((train_dir/'state.json').read_text()) if (train_dir/'state.json').exists() else None
        if not state or state['next_pair']<epoch*pairs:
            subprocess.run(command,check=True,cwd=ROOT)
        checkpoint=train_dir/f'checkpoint-{epoch*pairs}'/'policy'
        if not (checkpoint/'adapter_model.safetensors').exists():raise RuntimeError('Missing epoch checkpoint')
        evaluate(f'epoch-{epoch}',checkpoint)
    best=choose_checkpoint(evaluations)
    write_json(out/'complete.json',dict(epochs=5,steps=5*pairs,evaluated=True,
        selected_adapter=best['adapter'],selected_checkpoint=best['checkpoint'],
        development_solved=best['solved'],development_tasks=best['tasks'],
        caveat='Small failure-enriched development set used for selection; not a final generalization benchmark'))
    write_json(out/'progress.json',dict(stage='complete',selected_checkpoint=best['checkpoint']))
    print(json.dumps(dict(event='complete',selected_checkpoint=best['checkpoint'],adapter=best['adapter'])),flush=True)

if __name__=='__main__':main()
