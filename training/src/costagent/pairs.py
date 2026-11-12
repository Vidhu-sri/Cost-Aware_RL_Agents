"""Cheap trajectory-pair DPO selection. No pairs across tasks or policies."""
from collections import defaultdict
from itertools import combinations
import random


def build_pairs(records, delta=.1, seed=0):
    groups = defaultdict(list)
    for r in records:
        if r['source'] != 'swe_rebench': raise ValueError('Eval leakage')
        if r['solved'] is None: continue
        groups[(r['task_id'],r['sampling_policy'])].append(r)
    types = {'efficiency': [], 'competence': []}
    for group in groups.values():
        for a,b in combinations(group,2):
            if a['rollout_id'] == b['rollout_id']: continue
            if a['solved'] and b['solved']:
                chosen,rejected = sorted([a,b], key=lambda r:r['cost'])
                if rejected['cost']-chosen['cost'] <= delta: continue
                kind = 'efficiency'
            elif a['solved'] != b['solved']:
                chosen,rejected = (a,b) if a['solved'] else (b,a); kind = 'competence'
            else: continue
            ca,ra = chosen['messages'],rejected['messages']; n=0
            while n < min(len(ca),len(ra)) and ca[n] == ra[n]: n+=1
            if not n or n == len(ca) or n == len(ra): continue
            types[kind].append(dict(prompt=ca[:n], chosen=ca[n:], rejected=ra[n:],
                                    task_id=a['task_id'], source='swe_rebench', type=kind,
                                    variant='cheap_trajectory_pair', delta_C=rejected['cost']-chosen['cost'],
                                    delta_Q=None, chosen_id=chosen['rollout_id'], rejected_id=rejected['rollout_id']))
    rng=random.Random(seed)
    for rows in types.values(): rng.shuffle(rows)
    # Balance only when both types exist; report the missing type to the caller.
    if all(types.values()):
        n=min(map(len,types.values())); types={k:v[:n] for k,v in types.items()}
    return types['efficiency']+types['competence']
