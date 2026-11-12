# Comparing adapters in the Docker harness

Collect a frozen evaluation task list with each adapter, identical task/seed combinations, image commits, sampling settings and tool/time budgets. Keep these tasks out of all training and checkpoint selection. Record adapter paths/hashes with the collection. Run arms under comparable GPU conditions; shared GPU load affects wall time. This report does not itself run inference or certify split provenance.

The comparator accepts the SWE collector's manifest.json/effective_manifest.json, whose attempts explicitly index result directories. It never recursively mixes retries or selects the best run. For old Kaggle indexes use `--source kaggle_dev`; unknown seeds/latency remain missing, and unseeded pairs cannot be compared.

```bash
cd /home/mahesh/mahesh/tmp/Gemma4_Developer_Agent
PYTHONPATH=training/src python -m costagent.compare_runs \
  --arm baseline=artifacts/eval-base/manifest.json \
  --arm sft=artifacts/eval-sft/manifest.json \
  --arm rl=artifacts/eval-rl/manifest.json \
  --baseline baseline \
  --output artifacts/evaluation-comparison
```

Outputs: `report.md` (readable tables), `comparison.json` (paired estimates, task-bootstrap 95% intervals and coverage), `rollouts.csv` (one row per indexed rollout). A single `--arm` generates a descriptive baseline audit. No baseline-versus-tuned claim is generated until both real evaluations exist. Use `--baseline sft` to isolate subsequent RL gains.

Measures: solve rate, generated tokens, prompt tokens, cached prompt tokens, total model tokens, agent wall seconds, all/charged tool calls, explicit file reads, unique explicitly read/touched paths, shell calls. Submission and status calls are excluded only from charged calls.

File counts are lower-bound proxies: shell commands can access files without read_file, and relative/absolute aliases are not resolved. A precise all-file-access metric would require instrumentation inside the sandbox. Agent wall time excludes grading/server startup and is not model-only inference time.

Optional `--tokenizer /local/model/path` counts serialized observation text using the local tokenizer (no GPU/download). This is not claimed to be exact model-visible observation tokens. Prompt tokens repeatedly count carried context and must not be substituted for unique observations.

Pairs match task AND seed, validate commits/budgets/sampling/image, and reject duplicates. Missing configuration requires explicit `--exploratory`; the report records mismatches. Unmatched runs and unknown outcomes are counted. Paired metrics exclude unknown outcomes and use the same availability mask on both arms. Task means receive equal weight, and bootstrap resamples tasks, not correlated attempts. Both all-graded and both-solved cohorts are shown. A single task has no confidence interval. Solve-rate delta is in fraction units (multiply by 100 for percentage points); percentage change is relative. These intervals do not establish training-seed reproducibility or causal latency improvements.

Validation on the existing baseline is at `artifacts/evaluation-baseline-audit`. It is a historical data audit, not a held-out result for a trained adapter.
