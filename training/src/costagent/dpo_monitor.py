"""Clearly separate training-pair diagnostics from graded development results."""
import math
from statistics import mean


def training_metrics(scores,reference,pairs,rollouts,beta=.1,alpha=1.):
    margins=[];losses=[];nll=[]
    for pair in pairs:
        c,r=pair['chosen'],pair['rejected']
        margin=(scores[c]-scores[r])-(reference[c]-reference[r]);margins.append(margin)
        count=sum(sum(t['assistant_mask'][1:]) for t in rollouts[c]['turns'])
        chosen_nll=-scores[c]/count;nll.append(chosen_nll)
        x=beta*margin
        losses.append(max(-x,0)+math.log1p(math.exp(-abs(x)))+alpha*chosen_nll)
    return dict(split='training_pairs_not_validation',pairs=len(pairs),mean_loss=mean(losses),
                mean_margin=mean(margins),mean_chosen_nll=mean(nll),
                preference_accuracy=mean(1. if m>0 else .5 if m==0 else 0. for m in margins))


def choose_checkpoint(evaluations):
    """Keep the starting SFT on ties; never favor failed runs for being cheap."""
    best=evaluations[0]
    def key(row):
        return row['solved'], -row['mean_calls_solved'] if row['solved'] else 0.
    for row in evaluations[1:]:
        if key(row)>key(best):best=row
    return best
