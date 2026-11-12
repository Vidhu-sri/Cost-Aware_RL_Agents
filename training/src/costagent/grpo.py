"""GRPO statistics and the assistant-token clipped objective."""
from statistics import mean, pstdev


def advantages(values):
    if len(values) < 2: raise ValueError('GRPO requires sibling rollouts')
    std = pstdev(values)
    if std == 0: return None
    avg = mean(values)
    return [(x-avg)/(std+1e-6) for x in values]


def step_advantages(returns):
    """Normalize at each turn among siblings that actually reached that turn."""
    output = [[None]*len(row) for row in returns]
    for t in range(max(map(len, returns), default=0)):
        present = [(i,row[t]) for i,row in enumerate(returns) if t < len(row)]
        if len(present) < 2: continue
        a = advantages([v for _,v in present])
        if a is not None:
            for (i,_),value in zip(present,a): output[i][t] = value
    return output


def clipped_loss(logps, old_logps, reference_logps, advantage, mask, epsilon=.2, beta=.04):
    import torch
    if not mask.any(): raise ValueError('No assistant-generated tokens')
    ratio = (logps-old_logps.detach()).exp()
    advantage = torch.as_tensor(advantage, device=logps.device, dtype=logps.dtype)
    surrogate = torch.minimum(ratio*advantage, ratio.clamp(1-epsilon,1+epsilon)*advantage)
    # k3 sample estimator of forward KL under the current policy.
    delta = reference_logps.detach()-logps
    kl = delta.exp()-delta-1
    # Data came from the old policy: importance-weight the sampled KL.
    weighted_kl = ratio * kl
    return ((-surrogate + beta*weighted_kl)*mask).sum()/mask.sum(), {
        'kl': float((weighted_kl.detach()*mask).sum()/mask.sum()),
        'clip_fraction': float((((ratio.detach()-1).abs()>epsilon)*mask).sum()/mask.sum())}
