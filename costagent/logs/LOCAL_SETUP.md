# Local integration

- Training env: existing gdac (Python 3.13), Torch 2.6.0+cu124, Transformers 5.20.1. No conda env was created; gemma-harness was not modified.
- config.env points to existing QAT checkpoint. Training explicitly dequantizes it to BF16; this is not an unquantized original model or NF4 training.
- A0 collection used a bounded Python Docker evaluator, not a standalone swegemma eval invocation. scripts/eval_existing_docker.py wraps a frozen copy of that evaluator with submission/output overrides. It needs validation on the first real evaluation.
- Additional collection disabled (COLLECT=0); use indexed old SWE and newly collected attempts. Kaggle A0 remains evaluation in this package's builders.
- Parser preserves direct ATIF tool observations; ambiguous multi-call observations and unknown outcome records are excluded with logs, not converted to failure labels. Context reconstruction remains approximate.
- New gdac GPU library files and generated artifacts/results reside under /tmp because shared /home filled during setup. Preserve /tmp/gdac-training-libs-20261102 and /tmp/costagent-pipeline-20261102. Copy completed checkpoints to persistent storage when space is available.
- GPU stages wait until <=6000 MiB is in use, for at most 48 hours. Only the recorded owned vLLM process group is stopped; no global pkill.
- A6b is this package's offline listwise surrogate, not online GRPO. Its coefficients are fixed at the initial/reference score as designed by the supplied code. Do not label it exact iterative DPO or GRPO.
