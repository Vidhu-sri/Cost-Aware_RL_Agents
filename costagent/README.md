# costagent: cost-aware preference training for the Gemma 4 agent

## Run it
```bash
tar xzf costagent.tgz && cd costagent
cp config.env.example config.env      # fill in paths (5 minutes)
conda create -n train python=3.12 -y && conda activate train
pip install -r requirements-train.txt
python -m costagent.traces inspect <one of your results dirs>   # check the trace parse looks right
mkdir -p logs && nohup bash scripts/run_all.sh > logs/run_all.log 2>&1 &
tail -f logs/run_all.log
```
Result: `results/REPORT.md` (table with CIs, Pareto plot, data used, training curves, skipped/failed arms).

## What it does (in order, resumable)
1. CPU tests (listwise = DPO at n=2, surrogate gradient = autograd, unbiased turn sampling, gate, cost).
2. Optional extra rollouts on your SWE-rebench tasks: base at T=0.7, plus RLCD p+/p- prompts.
3. Parses every results dir, calibrates cost on training data only, builds SFT set, listwise groups,
   sibling pairs and gated RLCD pairs. Kaggle tasks are asserted out of every training file.
4. Evaluates A1 (stop-loss prompt), then trains and evaluates each arm the data supports:
   A2 RFT-lite, A6b listwise kappa=5, A6b kappa=0 (cost-blind ablation), A6a hard pairs (DPO), A6d RLCD.
   Arms without enough data are skipped with the reason written to the report.
5. Stats vs A0 and the report.

Rerunning `scripts/run_all.sh` skips finished steps. Delete `artifacts/done/<step>` to redo one.

## Things that can go wrong, and where you see it
- Trace format differs from ATIF: `traces inspect` shows the parse; `data_report.md` warns on empty trajectories.
- Chat template can't render the rebuilt history: `skipped turns: template_prefix_mismatch` in the data report.
- Adapter doesn't fit the served QAT model: `check_adapter.py` fails the eval step (logs/eval_<arm>.log).
- GPU busy when training starts: the step fails with the process list. Set VLLM_STOP_CMD.
- `--load nf4` needs bitsandbytes and a GPU; training weights are the bf16 checkpoint (TRAIN_MODEL).
