"""Bounded costs, outcome-gated rewards and graph potential shaping."""
import math
from statistics import median

WEIGHTS = dict(calls=.35, tokens=.35, files=.1, tests=.15, dups=.05)


def cost(counts, baseline, weights=WEIGHTS, cmax=1.0):
    if cmax <= 0 or any(v < 0 for v in weights.values()) or not math.isclose(sum(weights.values()), 1):
        raise ValueError('Invalid cost calibration')
    if any(not math.isfinite(counts[k]) or counts[k] < 0 for k in weights):
        raise ValueError('Counts must be finite and nonnegative')
    return sum(w * min(counts[k]/max(baseline[k], 1), cmax)/cmax for k,w in weights.items())


def calibrate(records):
    """Caller supplies exact counts and baseline-policy provenance; no eval fitting."""
    if not records or any(r['source'] != 'swe_rebench' or r['policy'] != 'base' for r in records):
        raise ValueError('Calibration requires train base-policy records')
    successes = [r for r in records if r['solved'] is True]
    if not successes: raise ValueError('No successful base rollouts for calibration')
    global_median = {k: median(r['counts'][k] for r in successes) for k in WEIGHTS}
    by_task = {t: {k: median(r['counts'][k] for r in successes if r['task_id'] == t) for k in WEIGHTS}
               for t in sorted({r['task_id'] for r in successes})}
    return global_median, by_task


def rewards(solved, c, potentials, lam=.5, eta=.1, gamma=1.0):
    if type(solved) is not bool or not 0 <= c <= 1 or not 0 <= lam < 1 or not 0 <= eta < 1-lam:
        raise ValueError('Invalid label/cost/lambda/eta')
    if not 0 <= gamma <= 1 or not potentials or potentials[0] != 0:
        raise ValueError('Potential must start at zero; gamma in [0,1]')
    if any(not 0 <= x <= 1 for x in potentials) or any(a > b for a,b in zip(potentials,potentials[1:])):
        raise ValueError('Potential must be bounded and nondecreasing')
    r2 = float(solved)*(1-lam*c)
    shaping = [gamma*b-a for a,b in zip(potentials,potentials[1:])]
    return dict(R1=float(solved), R2=r2, R2_ungated=float(solved)-lam*c,
                R3_traj=r2+eta*sum(shaping),
                R3_rtg=[r2+eta*sum(shaping[i:]) for i in range(len(shaping))])
