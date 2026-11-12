#!/usr/bin/env bash
# Calls the existing observed SWE worker, preserving source task specifications.
# This collects request logs, but exact response-token capture must be added before training.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${HARNESS_PYTHON:-/home/mahesh/miniconda3/envs/gemma-harness/bin/python}"
K="${K:-16}"
SEED="${SEED:-42}"
if [[ "${1:-}" != "--run" ]]; then
  echo "Dry run: K=$K seeded samples per authoritative train task; writes artifacts/samples/."
  echo "Use --run with the baseline vLLM server on port 8001 and Docker available."
  exit 0
fi
"$PYTHON" - "$ROOT" "$K" "$SEED" <<'PY'
import json,sys,subprocess
from pathlib import Path
root=Path(sys.argv[1]);k=int(sys.argv[2]);seed=int(sys.argv[3])
if k<2: raise ValueError('K must be at least 2')
batch=root/'swe-rebench-work/results/gemma100-v2-20261021'
for i,task in enumerate(sorted(json.loads((batch/'effective_manifest.json').read_text())['tasks'])):
    spec=batch/'tasks'/task/'grading_spec.json'
    for j in range(k):
        out=root/'artifacts/samples'/task/f'seed-{seed+i*k+j}'
        if out.exists(): raise RuntimeError(f'Refusing to overwrite {out}')
        out.mkdir(parents=True)
        subprocess.run([sys.executable,str(root/'swe-rebench-work/run_batch.py'),'--worker',
                        '--spec',str(spec),'--out',str(out),'--run','costagent-sampling',
                        '--seed',str(seed+i*k+j),'--phase','attempt'],check=True)
PY
