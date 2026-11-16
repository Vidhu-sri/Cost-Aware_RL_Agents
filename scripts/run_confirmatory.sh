#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONUNBUFFERED=1
exec /home/mahesh/miniconda3/envs/gemma-harness/bin/python -u scripts/confirmatory.py "$@"
