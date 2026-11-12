"""Fail-closed interface for verified, per-request tokenized training captures.

Raw ATIF is audit data, not an exact model-token capture. This contract deliberately
requires evidence that a producer compared its rendering to the served prompt.
"""
import json
from pathlib import Path
from .traces import TRAIN, read_json


def allowed_tasks(index=TRAIN):
    return set(read_json(index)['tasks'])


def validate_turn(turn):
    ids,mask=turn['input_ids'],turn['assistant_mask']
    if not 1 < len(ids) <= 32768 or len(ids) != len(mask): raise ValueError('Invalid token/mask length')
    if any(type(i) is not int or i < 0 for i in ids): raise ValueError('Invalid token IDs')
    if any(x not in (0,1) for x in mask) or mask[0] or not any(mask): raise ValueError('Invalid assistant mask')
    if turn.get('template_roundtrip') is not True: raise ValueError('Template round-trip not verified')
    for field in ('request_sha256','response_sha256','template_sha256'):
        value=turn.get(field,'')
        if len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError(f'Missing capture provenance: {field}')


def load_dataset(path, mode, allowed):
    records=[json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    if not records: raise ValueError('Empty training dataset')
    seen=set()
    for row in records:
        if row['source']!='swe_rebench' or row['task_id'] not in allowed: raise ValueError('Eval/unknown task rejected')
        if mode=='dpo':
            if row.get('variant') != 'cheap_trajectory_pair': raise ValueError('Unsupported DPO variant')
            for key in ('chosen_turns','rejected_turns'):
                if not row[key]: raise ValueError('Empty continuation')
                for turn in row[key]: validate_turn(turn)
            if not row.get('shared_prefix_sha256'): raise ValueError('Missing common-prefix provenance')
        else:
            identity=(row['task_id'],row['rollout_id'])
            if identity in seen: raise ValueError('Duplicate rollout')
            seen.add(identity)
            if type(row['solved']) is not bool or not 0<=row['cost']<=1: raise ValueError('Unknown label/cost')
            if row.get('calibration_source')!='swe_rebench': raise ValueError('Calibration leakage')
            if not row.get('sampling_policy_sha256') or not row.get('group_id'): raise ValueError('Missing sampling provenance')
            if not row['turns']: raise ValueError('Empty rollout')
            for turn in row['turns']: validate_turn(turn)
            if len(row['potentials']) != len(row['turns'])+1: raise ValueError('Potential/turn alignment')
    return records
