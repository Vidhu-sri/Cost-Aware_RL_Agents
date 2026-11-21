# Data report

- trajectories: 50 (train 50, kaggle eval 0)
- training tasks: 10; rollouts per task: min 5, max 5
- training successes: 34 / 50
- kaggle eval solved: 0 / 0
- variants: base=50, pos=0, neg=0
- cost calibration: c_max=2.00, tasks with a success baseline=10
- SFT (RFT-lite) trajectories: 10, turns: 78
- listwise groups: 10 (candidates 49)
- sibling pairs: 11 (competence 5, efficiency 6)
- RLCD pairs: 0 (dropped for prompt leakage: 0)
- skipped turns: {'template_prefix_mismatch': 28}
- all inputs are reconstructed from traces (approx=True); compaction approximated by dropping oldest history
