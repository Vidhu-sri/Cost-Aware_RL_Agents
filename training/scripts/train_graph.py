#!/usr/bin/env python3
"""Train with graph potential shaping (R3_traj or R3_rtg), using the GRPO loop."""
import sys
from train_grpo import main
if __name__=='__main__':
    if '--reward' not in sys.argv and not any(x.startswith('--reward=') for x in sys.argv):
        sys.argv += ['--reward','R3_rtg']
    main()
