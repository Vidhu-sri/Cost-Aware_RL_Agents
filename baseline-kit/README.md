# Official Gemma sample baseline on one A100, without Docker

Prepared 11 October 2026. This kit runs on your compute server; it is not a competition submission. It does not include model weights or competition data. Scripts were inspected and syntax checked. Deadline/normal-completion watchdog paths and interception argument/fingerprint checks were tested here. This environment could not complete a real Bubblewrap namespace probe (its /proc namespace access failed); your server has already demonstrated working network namespaces, but must run this kit's stricter probe. The complete GPU/harness execution remains untested here.

## What is reproduced

The official Ryan Holbrook Getting Started notebook, version 2, was read directly. It mounts `google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2`, uses `VllmServer`, BF16 on supported GPUs, context 32768, Gemma4 tool and reasoning parsers, auto tool choice, LoRA enabled with eight slots and rank ceiling 128, and the **subprocess** backend for the public sample. It copies the sample submission and changes sampling.yaml to temperature 0.2, top_p 0.95, max_output_tokens 16384, thinking_budget 4096, include_thoughts true. Its context compaction interval is 15 and overlap is 2. This kit follows those values and reads budgets from your sample's eval_config.yaml.

Differences: one A100 and tensor parallelism 1 rather than four L4s; GPU memory fraction 0.50 rather than the notebook's 0.90; at most one concurrent model sequence and one task; Bubblewrap and additional resource safeguards. Your installed vLLM may differ from the official wheel (you needed a compatible glibc build). The kit records versions; it does not claim bit-identical generations or official-equivalent timing. Model-instance version 2 identifies the weights more precisely than an unpinned Hugging Face main branch. It uses the checkpoint's native compressed-tensors quantization; do not add bitsandbytes, AWQ, GPTQ, or a second quantization flag.

The earlier 15.5GB calculation was only an idealized 4-bit weight floor, not a measured model footprint. Some layers are not quantized and there are scales and runtime allocations. Startup logs, not that arithmetic, determine actual memory use.

## Network and filesystem design

The trusted harness makes HTTP requests to vLLM at `127.0.0.1:8001/v1` in the host namespace. Every repository command, dependency-install command issued through the task manager, and Phase 2 test command runs in its own Bubblewrap network/PID/mount namespace. Such commands cannot reach the internet **or the host vLLM port**. A blanket network namespace around the whole harness would also break model access; that is why the boundary is at task command execution.

Each command sees system executables/libraries and the active conda environment read-only, only its private task root writable, and task wheels read-only. It does not bind `/` or your home directory. `/proc` and `/dev` are fresh; host CUDA device files and `/sys` are not mounted. No host credentials are passed to task commands. A sanitized task environment forces offline pip. The controller disables telemetry but retains host networking for model HTTP; that controller is trusted. vLLM offline environment flags are not kernel-level network isolation.

The runtime interception targets the exact `SubprocessManager.exec` implementation independently inspected in the official **swegemma 0.2.11 wheel** downloaded from the official wheelhouse. It does not edit installed packages or sample prompts. A source fingerprint mismatch stops execution rather than guessing at integration. Python 3.12 reproduces the notebook host, but is not the official Docker test image's Python 3.13: some tasks may need separate dependency/Python treatment.

## 1. Put the kit beside your existing data

Download this ZIP to your server and extract it in the project directory above `data`:

```bash
cd /home/mahesh/mahesh/tmp/Gemma4_Developer_Agent
python -m zipfile -e /path/to/gemma_a100_baseline.zip .
cd baseline-kit
conda activate gemma-harness
python -m pip install kagglehub psutil
mkdir -p logs
python -m pip freeze > logs/environment.txt
python -c "import vllm; print(vllm.__version__)"
```

Expected data paths: `../data/tasks.jsonl`, `snapshots/`, `sample_submission/`, `graphs/`, `embeddings/`, and `wheels/`. `wheels/` is the per-task dependency collection, not the vLLM/harness `wheelhouse/`. Keep downloaded task setup resources, including `sandbox/setup.py` when supplied. Do not bulk pip-install all historical task wheels into your harness environment. No Docker, Podman, sudo, or systemd resource delegation is needed.

## 2. Download the exact model used by the starter

Authenticate using your existing Kaggle credentials. If you have not accepted the Gemma model terms, visit the model page and complete the account/license steps yourself. Never put an API token in logs or chat.

```bash
python download_model.py
```

This writes `model-path.txt` and `model-source.json`; kagglehub downloads/caches the full model. Downloads happen before sandboxed evaluation. You need enough disk space for the model and extracted task environments. No model-download operation occurs during agent/test execution.

## 3. Verify Bubblewrap before using the GPU

```bash
python supervise.py --seconds 120 --rss-gib 2 --processes 64 -- \
  python run_baseline.py --data ../data --mode probe
```

The probe checks a different network namespace, only loopback visible, a host file hidden, internet and host-model connections blocked, and timeout exit 124. It creates/cleans a disposable task venv. If this fails, stop and read the error. Never silently rerun without Bubblewrap.

If you see a source-fingerprint error, the installed harness differs. Collect the version and source, then adapt the kit to that actual wheel before running:

```bash
python - <<'PY'
import inspect, importlib.metadata
import swegemma.sandbox.subprocess as s
print(importlib.metadata.version('swegemma'))
print(inspect.getsource(s.SubprocessManager.exec))
PY
```

Do not disable the fingerprint check to force execution.

## 4. Validate test provisioning with the published reference patch

Use the same task for reference validation and the sample smoke run. Default is the first task from tasks.jsonl, matching the starter's initial task selection. Reference mode bypasses the LLM and applies the task's published gold patch through the harness verification path. Gold patches stay in the trusted controller and are not mounted into the agent command environment. This is a development check, never an inference-time tool or submitted agent.

```bash
python supervise.py --seconds 1800 --rss-gib 8 --processes 128 -- \
  python run_baseline.py --data ../data --mode reference --label sample-01 \
  > logs/reference-01.log 2>&1
```

Inspect `logs/reference-01.log` and `results/sample-01-reference/test_outputs/`. A reference failure is not proof the agent/model is bad. Diagnose missing imports, incompatible wheel tags, Python-version mismatch, setup failures, patch application, or watchdog termination. Exit 2 alone is not a unique indicator of missing dependencies. If packages must be downloaded, obtain the correct task-specific versions outside the sandbox and stage them in the task dependency collection, then rerun reference validation under a fresh label. Do not enable network access during verification. A passing reference validates this task's provisioning only, not all tasks.

## 5. Start vLLM on the A100

The default fraction is **0.50 of the whole 80GB GPU**, roughly a 40GiB engine budget, not 50% of currently free memory. Use it only if that budget is within the GPU share you may use. It caps neither GPU compute usage nor all transient startup allocations. Do not automatically raise it after an OOM. The existing 15GB use belongs to another/current process; leave it alone.

```bash
nohup bash serve.sh > logs/vllm-base.log 2>&1 &
echo $! > logs/vllm-base.pid
tail -n 80 -f logs/vllm-base.log
```

Ctrl-C stops tail, not the server. The server is loopback-only on 8001; the service on 8000 is untouched. After it reports readiness, in another terminal:

```bash
curl --fail --max-time 10 http://127.0.0.1:8001/v1/models
```

Expected model ID: `gemma-4-31b-it-qat-w4a16-ct`. If startup reports an unsupported flag/parser, backend error, driver/CUDA incompatibility or insufficient KV cache, preserve the error and fix the specific issue. This kit does not promise that your presently installed vLLM imports or serves successfully. Avoid changing model quantization or reducing context silently: that changes the experiment.

Test an actual generation:

```bash
curl --fail --max-time 120 http://127.0.0.1:8001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gemma-4-31b-it-qat-w4a16-ct","messages":[{"role":"user","content":"Reply with OK."}],"max_tokens":128,"temperature":0}'
```

This is connectivity/generation verification, not the benchmark. Full thinking may consume the small generation allowance, so do not require an exact `OK` string as the health criterion. Tool-call parsing is exercised by the next sample run.

## 6. Run one sample-submission task

```bash
python supervise.py --seconds 1800 --rss-gib 8 --processes 128 -- \
  python run_baseline.py --data ../data --mode baseline --label sample-01 \
  > logs/baseline-01.log 2>&1
```

In another terminal:

```bash
tail -n 80 -f logs/baseline-01.log
```

Use `--task-id INSTANCE_ID` in both reference and baseline commands to select another task. Labels must be new for reruns. The script copies the sample into each result folder, applies the official notebook's sampling change, reads its original evaluation budgets, registers the exact served model alias through ModelRegistry/LiteLlm, and runs Evaluator with concurrency 1. No LoRA adapter is loaded for this baseline. The sample's usual one-minute/ten-tool budget is a smoke test and may produce no patch, as the published starter itself did; do not treat a zero one-task score as a meaningful estimate of model quality.

## 7. Read and preserve the result

```bash
cat results/sample-01-baseline/summary.json
cat results/sample-01-baseline/task_results.jsonl
```

Preserve the original task IDs, `agent_snapshot/`, `run_manifest.json`, server startup log, environment snapshot, patches, test outputs and traces when written by the harness. A successful smoke test means the model responds, tools execute inside isolation, a result is saved, and any failures can be explained. A one-task failure need not produce a patch; choose a modest multi-task held-out cohort next to measure solve rate. Reference results must not count toward the agent's solve rate.

Local base-vs-adapter comparisons must use identical tasks, prompts, tools, sampling, budgets, model revision, and sandbox provisioning. Run them sequentially and record interference from other GPU jobs. Local wall times are not official four-L4 timings. Increasing the one-minute sample budget creates a new experiment and requires rerunning both base and adapter with that new budget.

## 8. Stop your model server

Check the recorded PID and its command before signalling it; never kill another user's processes:

```bash
ps -p "$(cat logs/vllm-base.pid)" -o pid,args
kill -TERM "$(cat logs/vllm-base.pid)"
```

Check nvidia-smi afterward. If an engine child remains, identify it from this launch's process tree before stopping it; do not use a blanket pkill vllm. The evaluation watchdog does not supervise the separately launched model server.

## Protection limits on this server

- Each task command: kernel network/mount/PID isolation; no host GPU devices; command deadline at most 300s (also covers verification calls that omit a timeout); per-process 6GiB address-space cap and 512MiB single-file cap; core dumps disabled; thread environment values 1.
- Evaluation job: one task; two CPUs from the inherited allowed affinity; nice +10; watchdog checks every 0.2s for 8GiB summed RSS, 128 processes, or 30-minute deadline. Namespace monitors and observed descendants are killed on termination.
- The watcher is reactive, RSS sums double-count some shared pages, affinity limits eligible CPUs rather than guaranteeing a CPU quota, and process discovery can race. These are **not** hard aggregate cgroup limits or fork-bomb protection. No hard aggregate disk cap is provided. Venv creation and trusted file-copy/setup orchestration happen on the controller; repository code executes in guarded commands. PID namespace teardown removes command descendants, including children that change process groups.
- Task shells are ephemeral: background services cannot persist across separate tool calls. This can change behavior for tasks that require such services. This is a guarded development baseline, not a replacement for the official Docker security boundary or exact grading runtime.

Do not start parallel RL rollouts on the strength of this smoke-test kit. First obtain measured resource use and a known allocation. The kit is intended to make one task concrete and inspectable under your current constraints.

## Verified source references

- Official starter notebook (directly read, version 2): https://www.kaggle.com/code/ryanholbrook/getting-started-gemma-4-developer-agent
- Official model instance mounted there: `google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2` (download through kagglehub).
- Official wheelhouse: https://www.kaggle.com/datasets/metric/gemma-4-developer-agent-wheelhouse — inspected swegemma 0.2.11, adk_submission 0.2.13, adk_eval_core 0.1.0 source, including execution cleanup and Gemma4 reasoning delimiters.
- Google checkpoint config cross-check: https://huggingface.co/google/gemma-4-31B-it-qat-w4a16-ct/raw/main/config.json
- Kagglehub model download API: https://github.com/Kaggle/kagglehub
- Bubblewrap isolation and its limits: https://github.com/containers/bubblewrap

Do not assume the latest competition resources are identical forever. Keep the recorded model version and installed wheel versions with every result.
