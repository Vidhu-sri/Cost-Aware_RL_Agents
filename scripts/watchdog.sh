#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec /home/mahesh/miniconda3/envs/gemma-harness/bin/python -u "$ROOT/scripts/watchdog_v2.py" "$@"
