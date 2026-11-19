#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GDAC_STATUS_ROOT="$ROOT"
/home/mahesh/miniconda3/envs/gemma-harness/bin/python - <<'PY'
import datetime as dt
import glob
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

out = Path(os.environ['GDAC_STATUS_ROOT']) / 'results/dpo_live_v2'
files = [Path(p) for p in glob.glob(str(out / 'attempts/*/DPO/done.json'))
         if not Path(p).parent.parent.name.startswith('smoke-')]
rows = []
for path in files:
    try:
        rows.append((path, json.loads(path.read_text())))
    except (OSError, ValueError):
        pass
count = len({(r.get('task_id'), r.get('arm')) for _, r in rows})
last = max((p.stat().st_mtime for p, _ in rows), default=None)
last_text = (dt.datetime.fromtimestamp(last, ZoneInfo('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M IST')
             if last else 'none')
durations = [float(r['elapsed_controller_seconds']) / 60 for _, r in rows
             if isinstance(r.get('elapsed_controller_seconds'), (int, float))]
mean = sum(durations) / len(durations) if durations else None
eta = mean * max(0, 84 - count) if mean is not None else None
restarts = 0
log = out / 'WATCHDOG.log'
if log.exists():
    restarts = sum(' RESTART ' in line for line in log.read_text(errors='replace').splitlines())
alert = ' ALERT' if (out / 'ALERT.txt').exists() else ''
eta_text = f'{eta / 60:.1f}h' if eta is not None else 'unknown'
mean_text = f'{mean:.1f}min' if mean is not None else 'unknown'
print(f'{count}/84 DPO last={last_text} mean={mean_text} ETA={eta_text} restarts={restarts}{alert}')
PY
