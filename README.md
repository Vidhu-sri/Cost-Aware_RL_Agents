# Cost-Aware Coding Agents

Code and results for studying preference training, adapter routing, and evaluation of a Gemma coding agent. The repository includes training and evaluation scripts, per-task result tables, and preregistrations. The experiments provide insights into agent training; see [results and limitations](paper-results/claims/CLAIMS.md).

## Requirements

- **For inspecting results:** Git and a text editor. CSV files can be opened in a spreadsheet. Python 3.12 is useful for the analysis scripts.
- **For model inference:** Linux, Docker, an NVIDIA GPU with CUDA-compatible drivers, vLLM, the Gemma 4 31B QAT model and the competition task data and harness. The recorded local experiments used one **80 GB A100**, sequential execution and a 32,768-token context. Memory and disk needs depend on the runtime and configuration; check free GPU memory and disk before starting.
- **For training:** an isolated Python environment with PyTorch, Transformers, PEFT and the packages listed in `costagent/requirements-train.txt`. The 31B model and training activations require substantial GPU memory; the original runs used an A100 80 GB. These requirements are not a tested minimum for other hardware.
- **Access:** the Gemma model is gated, and the [adapter artifacts](https://huggingface.co/silvix9/Cost-Aware-Gemma) may require separate authorization. Task data, model weights, Docker images and raw traces are not included in this Git repository.

## Setup

1. Clone this repository. The predeveloped harness is a pinned submodule; only initialize it, if working with SWE-rebench:

   ```bash
   git clone https://github.com/Vidhu-sri/Cost-Aware_RL_Agents.git
   cd Cost-Aware_RL_Agents
   git submodule update --init swe-rebench-work/publisher-harness
   ```

2. Create a **separate** training environment. Choose a PyTorch build compatible with your GPU and driver; the requirements are not a lockfile and do not guarantee the original runtime:

   ```bash
   conda create -n costagent-train python=3.12 -y
   conda activate costagent-train
   python -m pip install -r costagent/requirements-train.txt
   ```

   Install the `swegemma`, `adk_submission`, Docker SDK, vLLM and their compatible dependencies in a **separate harness environment**, using the competition's published wheelhouse. Do not install the per-repository test dependencies into that environment. The historical harness used `swegemma 0.2.11`; the project does not include a complete, portable environment lockfile.

3. Obtain the model, adapters and data under their respective access terms. [ARTIFACTS.md](ARTIFACTS.md) records the adapter revision, dataset provenance and checksums. Put the competition bundle in `data/` with its published directory structure. Keep dataset gold patches and grading metadata outside the agent-visible environment. Set paths in a local copy of `costagent/config.env.example`; never commit credentials.

4. Inspect the code and configuration before running on a new host. The historical scripts contain machine-specific absolute paths and settings and are **not a turnkey installation**. In particular, adapt `baseline-kit/serve.sh` for the model path, CUDA libraries and GPU allocation; do not copy its original compatibility-library path blindly. The Docker contexts in `baseline-kit/docker-context/` include dependency provenance and wheel checksums. Use a fresh label and validate a reference task before interpreting agent results. `baseline-kit/run_docker.py --help` documents the available local runner modes once the harness dependencies and data are installed.

   ```bash
   conda activate <your-harness-environment>
   python baseline-kit/run_docker.py --help
   ```

   Local Docker results are not guaranteed to reproduce the competition evaluator. On shared hardware, run sequentially, check resource availability, and clean up only containers and server processes belonging to your run.

## Results and layout

- [`paper-results/claims/`](paper-results/claims/CLAIMS.md): paired comparisons, scoring-rule sensitivity, patch classifications and per-task CSVs.
- [`paper-results/dpo_live_v2/`](paper-results/dpo_live_v2/REPORT.md): follow-up analysis, snapshot audit and protocol deviations.
- [`prereg/`](prereg/): registered plans, amendments and fixed-stop history. The full 84-task follow-up was previously exposed to baseline evaluation and is not an untouched holdout.
- [`costagent/`](costagent/): cost calculation, training, analysis and adapter-routing experiments.
- [`baseline-kit/`](baseline-kit/): local serving, Docker evaluation and monitoring. Its README also documents an earlier Bubblewrap workflow; it does not describe all later Docker experiments.
- [`training/`](training/): additional experimental training implementations and historical notes; not every planned method was completed.

Read [the evidence audit](paper-results/claims/PAPER_AUDIT_2026-11-19.md) before quoting results. A timeout can coexist with a passing final patch; an uninterpretable verification is not a verified failure. Individual raw trajectories, patches, test logs, private competition data and model weights are excluded from this repository, so the published tables alone cannot independently reproduce every original verification.
