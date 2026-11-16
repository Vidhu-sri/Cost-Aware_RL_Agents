"""Freeze an evaluation plan; read-only with respect to all pilot artifacts."""
import hashlib, importlib.metadata as md, json, random, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'costagent/artifacts/mixed-temperature-v1/evaluation'
TRAIN=['fastapi_14492','fastapi_14786','httpx_3672','requests_7205','rich_3894']
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(8*1024**2),b''):h.update(block)
 return h.hexdigest()
def main():
 dest=ROOT/'prereg';assert not (dest/'frozen.json').exists(), 'Already frozen'
 records=[json.loads(x) for x in (ROOT/'data/tasks.jsonl').read_text().splitlines()]
 allids=[r['instance_id'] for r in records];pilot=json.loads((E/'test_tasks.json').read_text())
 ids=sorted(set(allids)-set(TRAIN)-set(pilot))
 assert len(allids)==len(set(allids))==129 and len(pilot)==len(set(pilot))==40
 assert not set(TRAIN)&set(pilot) and len(ids)==84, f'Expected 84: got {len(ids)}'
 rng=random.Random(20261116);rng.shuffle(ids)
 order=[{'task_id':t,'arms':['A0','router'] if rng.getrandbits(1)==0 else ['router','A0']} for t in ids]
 a0=E/'paper40-20261106a-A0-test-seed-42/tasks/fastapi_14246'
 router=E/'method40-20261110a/rerun/fastapi_14246/tasks/fastapi_14246'
 eff=json.loads((a0/'effective_settings.json').read_text())
 rp=json.loads((E/'method40-20261110b/plan.json').read_text())
 files={}
 def keep(p,expected=None):
  p=Path(p);h=sha(p)
  if expected is not None:assert h==expected,f'Pilot mismatch: {p}: {h} != {expected}'
  files[str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)]=h
 for fn,key in [('method_router.py','router_sha256'),('phase_router.py','phase_sha256'),('docker_eval_worker.py','worker_sha256'),('container_monitor.py','monitor_sha256')]:keep(ROOT/'costagent/scripts'/fn,rp[key])
 for name,h in eff['agent_sha256'].items():
  if name!='configs/sampling.yaml':keep(ROOT/'data/sample_submission'/name,h)
 import yaml
 sam=yaml.safe_load((ROOT/'data/sample_submission/configs/sampling.yaml').read_text());sam['temperature']=.2
 encoded=yaml.safe_dump(sam)+'\nseed: 42\n'
 assert hashlib.sha256(encoded.encode()).hexdigest()==eff['effective_sampling_sha256']
 keep(ROOT/'data/sample_submission/configs/sampling.yaml')
 for item in rp['adapters'].values():
  for f,h in item['files'].items():keep(Path(item['path'])/f,h)
 for k,v in eff['packages'].items():assert md.version(k)==v,f'Package drift {k}'
 # Freeze installed harness sources, in addition to recorded release versions.
 for package in ['swegemma','adk-submission','adk-eval-core','google-adk']:
  dist=md.distribution(package)
  for f in dist.files or []:
   if str(f).endswith('.py'):keep(Path(dist.locate_file(f)).resolve())
 keep(ROOT/'model-source.json',eff['model_source_sha256'])
 keep(ROOT/'gemma-4-31b-it-qat-w4a16-ct/config.json',eff['model_config_sha256'])
 manifest=json.loads((a0/'run_manifest.json').read_text());keep(ROOT/'data/tasks.jsonl',manifest['tasks_sha256'])
 for t in ids+['fastapi_14246']:keep(ROOT/f'data/snapshots/{t}.tgz')
 for folder in ['costagent/scripts','baseline-kit']:
  for f in (ROOT/folder).glob('*.py'):keep(f)
 keep(ROOT/'costagent/scripts/serve_local.sh');keep(ROOT/'costagent/costagent/eval_status.py')
 for f in (ROOT/'baseline-kit/docker-context').glob('*/wheels/*.whl'):keep(f)
 images={}
 for image in ['gemma-requests-sandbox:20261015c','gemma-fastapi-sandbox:20261015a','gemma-rich-sandbox:20261015a','gemma-httpx-sandbox:20261015a']:
  images[image]=subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()
 # Assert every observed pilot image is unchanged.
 for row in json.loads((E/'method40-20261110-analysis/per_task.json').read_text()):
  if row['arm'] not in ['A0','Method router']:continue
  m=json.loads((E/row['task_dir_relative']/'run_manifest.json').read_text())
  assert images[m['image']]==m['image_id']
 plan={'version':1,'seed':20261116,'model_seed':42,'tasks':ids,'order':order,'training_excluded':TRAIN,'pilot_excluded':pilot,'smoke_task':'fastapi_14246','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'pilot_A0':str(a0),'pilot_router':str(router),'packages':eff['packages'],'effective_settings':eff,'router_plan':rp,'files':files,'images':images,'phase2_authorized':False}
 (dest/'frozen.json').write_text(json.dumps(plan,indent=2)+'\n')
 text='''# Confirmatory evaluation preregistration — 2026-11-16

This protocol is committed before any new model request (including smokes).
The final report records this commit. Existing pilot artifacts are immutable.

## Population and prior exposure
129 unique published dev IDs minus the five training IDs and the 40 matched pilot
IDs yields exactly 84. The sets are disjoint. This is a prospective comparison
outside the matched pilot, NOT a claim of never-seen tasks: the earlier 129-task
baseline covered these IDs. No selection uses those previous outcomes.
Training exclusion: fastapi_14492, fastapi_14786, httpx_3672, requests_7205, rich_3894.
The complete exclusions, file hashes, package versions, image IDs and pilot
source paths are in frozen.json. There is one seed, no retraining or tuning.

## Hypothesis and tests
Primary hypothesis: the method router resolves more tasks than the A0 sample agent.
Primary test: exact TWO-SIDED McNemar, alpha=0.05, on matched interpretable pairs
among all 84 tasks. Report excluded unknown pairs and IDs. Timeout and no-patch
are outcomes, not grounds for exclusion unless verification is uninterpretable.
Use the frozen pilot interpreter; a timeout can coexist with a verified pass.
Report baseline-only and router-only discordances; direction is router minus A0.
If no discordances, p=1. No interim arm comparisons or outcome-based stopping.

Secondary DESCRIPTIVE estimates: router-minus-A0 difference in calls per solve
and tokens per solve, with 20,000 PAIRED task-bootstrap draws, numpy default_rng
seed 20261116, percentile 95% intervals. Use the same complete interpretable
pairs for these paired differences. The per-arm all-84 tables include all attempt
costs (including unknowns) divided by verified passes; unknowns are not asserted
to be failures. Report Wilson 95% intervals for verified yield on all 84.
Billed calls exclude get_status/submit_patch; tokens sum trace prompt/completion
usage, including repeated context. Missing usage is flagged, never imputed as zero.
Zero solve ratios are undefined, not zero. Bootstrap draws with zero solves in
either arm are excluded, their fraction reported; suppress a finite interval
when that fraction is >=2.5%. No secondary significance claims.

Optional phase 2: DPO on these same 84 IDs in the same shuffled task order, ONLY
after phase 1 completes and the user confirms GPU hours remain. DPO vs A0 is
secondary; if run, report Holm-adjusted p-values across primary router-vs-A0 and
DPO-vs-A0 (as well as raw p-values). No automatic phase-2 execution.

## Frozen execution
A0 uses data/sample_submission unchanged. Router uses the same sample prompts,
original analyzer adapter, and the recorded RFT, DPO epoch-005, and SDPO contrast
epoch-005 adapters with the byte-identical method_router.py and phase_router.py.
Both: 5 minutes, 100 billed calls, 50 turns, 60-second command timeout; ordinary
sampling temperature .2, top-p .95, seed42, thinking4096, output cap16384.
Preserve pilot compaction and summary quirks: summary temperature1.0, top-k64,
and inherited uncapped summary requests. No context-limit bug fixes.
Router phase overrides remain exactly as saved (not a flat4096/16384 policy).

Use unchanged serve_local.sh, A10080GB, bfloat16/QAT base, context32768,
GPU fraction .60, max sequences1, max batched tokens4096, max LoRA rank128,
max LoRAs8, gemma4 tool/reasoning parsers, CUDA compatibility and FlashInfer
sampling disabled. A0 main_lora points to sample; router main_lora points to DPO
and loads rft_lora/dpo_lora/sdpo_lora. Restart the owned server when the arm changes
to preserve these distinct pilot launch configurations; reuse it for adjacent
attempts of the same arm. Server startup/probes are outside the agent budget.

Use unchanged Docker worker, offline network none, private namespace veth,
NET_ADMIN capability, no privileged mode, host network, Docker socket, or host
bind mounts; rootless cgroup-v1 has NO enforced aggregate CPU/memory caps.
900s outer deadline, outer process watchdog960s plus45s SIGINT/15s SIGTERM grace.
Monitor before worker starts; clean only each recorded run label's containers.
Pre-start free GPU >=62000MiB; stop on free GPU<8000MiB, host available<16GiB,
disk free<12GiB, observed container namespace RSS>12GiB, monitor/cleanup failure.
Summed process RSS is an observed metric, not a hard cgroup memory cap.

## Smoke, stopping, replacement and resumption
One fresh fastapi_14246 pilot smoke per arm, in A0/router order; excluded from
confirmatory statistics and retained only as infrastructure audit evidence.
No requirement that the patch solves; valid model responses, trace, terminal
record and monitor/cleanup suffice. Configuration identity must match pilot.
All84tasks, botharms, no additions or outcome-based reruns. Stop on an actual
permission/resource/configuration/monitor/cleanup failure; resume at the next
unfinished preregistered slot, never rerun a terminal record.
One replacement only when there is NO terminal record and documented GPU/vLLM/
Docker infrastructure failure. Preserve original partial files and log cause,
replacement linkage and timestamp. No retry for timeout, no patch, failed or
unknown verification, controller exception, or an exhausted replacement.
A hard outer timeout without outcome is recorded terminal unknown, never retried.
Unexpected incomplete slots without qualifying crash evidence require a stop.
Terminal outcome is checkpointed before resource checks so completed tasks cannot
be rerun after a stop. One process lock; one task/model job at a time. No processes
or containers outside this batch are stopped. A resumed batch refuses to steal
an occupied model port or kill an unverified PID. Checkpoint every result; emit
progress counts at least every30minutes without arm comparisons. Preserve all
raw outputs and anomalies. Analysis runs only once all168slots have terminal
records. Pooled pilot40+confirmatory84 table is DESCRIPTIVE, not the primary test.

## Exact randomized order
Start with lexicographically sorted eligible IDs. Python random.Random(20261116),
shuffle once, then one getrandbits(1) per shuffled task:0=A0 then router,
1=router then A0. The following concrete order, not an implementation-dependent
regeneration, is authoritative:

| Position | Task ID | First arm | Second arm |
|---:|---|---|---|
'''
 for i,row in enumerate(order,1):text+=f"| {i} | {row['task_id']} | {row['arms'][0]} | {row['arms'][1]} |\n"
 (dest/'CONFIRMATORY.md').write_text(text)
 print(json.dumps({'tasks':len(ids),'attempts':2*len(ids),'frozen_files':len(files),'first_pair':order[0]}))
if __name__=='__main__':main()
