#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
P=/home/mahesh/miniconda3/envs/gdac/bin/python
"$P" -m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
"$P" -m pip install -r requirements-train.txt 'torch==2.6.0' 'transformers==5.20.1' 'compressed-tensors==0.15.0.1'
"$P" -m pip check
