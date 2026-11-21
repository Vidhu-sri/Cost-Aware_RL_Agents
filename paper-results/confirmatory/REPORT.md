# Confirmatory evaluation

Preregistration commit: `2508c60f7f77fb5c4b9cb86a43e6b3092a999da1`.

Deviations: Pilot smoke outputs were retained as infrastructure audit evidence rather than discarded; both are excluded from all 168 confirmatory rows and pooled tables.

All 168 attempts completed. These 84 tasks are outside the matched pilot, but were previously covered by the 129-task baseline; 12 also appeared in checkpoint-development evaluations. This is prospective replication, not untouched held-out validation.

The two pilot smoke outputs were retained only for pipeline audit. A0 and router each sent model requests, produced captured traces, and cleaned up their containers. Neither smoke contributes to task counts or effect estimates.

## Primary result

Exact two-sided McNemar: n=77, baseline-only=3, router-only=6, p=0.507812.

Alpha = .05; one seed. Excluded uninterpretable pairs: fastapi_14186, fastapi_14262, fastapi_14609, fastapi_14978, fastapi_15030, rich_3772, rich_3930.

| Arm | N | Passes | Yield [Wilson 95%] | Mean calls | Mean tokens | Calls/solve | Tokens/solve | Timeouts | No patch | Unknown |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| A0 | 84 | 18 | 21.43% [14.01, 31.35] | 22.14 | 215,141.58 | 103.33 | 1,003,994.06 | 50 | 19 | 7 |
| router | 84 | 21 | 25.00% [16.97, 35.21] | 22.62 | 205,062.14 | 90.48 | 820,248.57 | 58 | 25 | 3 |

Ratios use costs of all 84 attempts divided by verified passes; unknowns remain separate. A timeout may coexist with a verified pass. Failed/cancelled model requests may have unrecorded tokens.

## Secondary descriptive paired differences

Router minus A0 on the 77 interpretable paired tasks; 20,000 paired task-bootstrap draws, seed 20261116. No secondary significance claim.

```json
{
  "paired_n": 77,
  "baseline_only": 3,
  "router_only": 6,
  "exact_two_sided_p": 0.5078125,
  "included_ids": [
    "fastapi_11194",
    "fastapi_11355",
    "fastapi_13207",
    "fastapi_13537",
    "fastapi_13713",
    "fastapi_13786",
    "fastapi_13920",
    "fastapi_14077",
    "fastapi_14099",
    "fastapi_14266",
    "fastapi_14303",
    "fastapi_14349",
    "fastapi_14360",
    "fastapi_14361",
    "fastapi_14371",
    "fastapi_14372",
    "fastapi_14419",
    "fastapi_14430",
    "fastapi_14448",
    "fastapi_14458",
    "fastapi_14459",
    "fastapi_14463",
    "fastapi_14482",
    "fastapi_14512",
    "fastapi_14583",
    "fastapi_14605",
    "fastapi_14791",
    "fastapi_14794",
    "fastapi_14851",
    "fastapi_14873",
    "fastapi_14962",
    "fastapi_14964",
    "fastapi_14986",
    "fastapi_15023",
    "fastapi_15280",
    "fastapi_15588",
    "fastapi_15589",
    "fastapi_15763",
    "fastapi_15800",
    "fastapi_5077",
    "fastapi_9425",
    "fastapi_9555",
    "requests_6589",
    "requests_6592",
    "requests_6757",
    "requests_7309",
    "requests_7315",
    "requests_7328",
    "requests_7427",
    "requests_7433",
    "requests_7502",
    "requests_7505",
    "rich_2725",
    "rich_3006",
    "rich_3043",
    "rich_3063",
    "rich_3105",
    "rich_3130",
    "rich_3180",
    "rich_3296",
    "rich_3454",
    "rich_3468",
    "rich_3469",
    "rich_3471",
    "rich_3486",
    "rich_3506",
    "rich_3518",
    "rich_3675",
    "rich_3777",
    "rich_3905",
    "rich_3934",
    "rich_3935",
    "rich_3942",
    "rich_3944",
    "rich_4075",
    "rich_4076",
    "rich_4079"
  ],
  "excluded_ids": [
    "fastapi_14186",
    "fastapi_14262",
    "fastapi_14609",
    "fastapi_14978",
    "fastapi_15030",
    "rich_3772",
    "rich_3930"
  ],
  "bootstrap_seed": 20261116,
  "resamples": 20000,
  "undefined_bootstrap_fraction": 0.0,
  "calls": {
    "difference": -12.65079365079366,
    "ci95": [
      -55.25913492971558,
      18.728208556149642
    ]
  },
  "tokens": {
    "difference": -175331.65079365077,
    "ci95": [
      -591207.8646130953,
      110396.81988283627
    ]
  }
}
```

## Router audit

Transitions exclude cached retries. Time/repeat/test select first SDPO takeover; exchange threshold counts transitions into DPO. Yield by first SDPO trigger is descriptive and not causal. Final adapter means last routed request.

```json
{
  "tasks": [
    {
      "task_id": "rich_3944",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 3
      },
      "decisions": 30,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14463",
      "resolved": true,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 17,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3930",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 1
      },
      "decisions": 12,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14372",
      "resolved": true,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 5
      },
      "decisions": 31,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14794",
      "resolved": true,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 19,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14371",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "successful_test",
      "transition_triggers": {
        "successful_test": 1
      },
      "condition_true_requests": {
        "successful_test": 3,
        "budget_240s": 2
      },
      "decisions": 13,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14458",
      "resolved": true,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 4
      },
      "decisions": 12,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_13713",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 10
      },
      "decisions": 43,
      "sticky_violation": false
    },
    {
      "task_id": "requests_6592",
      "resolved": false,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 33,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_15030",
      "resolved": null,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 3
      },
      "decisions": 21,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14962",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 1
      },
      "decisions": 27,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3905",
      "resolved": true,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 14,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_15280",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 5
      },
      "decisions": 38,
      "sticky_violation": false
    },
    {
      "task_id": "requests_7505",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 10
      },
      "decisions": 26,
      "sticky_violation": false
    },
    {
      "task_id": "rich_4079",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 13
      },
      "decisions": 47,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3180",
      "resolved": false,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 6,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14459",
      "resolved": false,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 14,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14186",
      "resolved": null,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 2
      },
      "decisions": 13,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3130",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 4
      },
      "decisions": 34,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14430",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 5
      },
      "decisions": 17,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_13786",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 2
      },
      "decisions": 16,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_13537",
      "resolved": true,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "successful_test",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "successful_test": 1
      },
      "condition_true_requests": {
        "successful_test": 1
      },
      "decisions": 16,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3942",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 2
      },
      "decisions": 16,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_5077",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 10
      },
      "decisions": 32,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14448",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 4
      },
      "decisions": 11,
      "sticky_violation": false
    },
    {
      "task_id": "rich_2725",
      "resolved": true,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "successful_test",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "successful_test": 1
      },
      "condition_true_requests": {
        "successful_test": 2
      },
      "decisions": 19,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14609",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 2
      },
      "decisions": 21,
      "sticky_violation": false
    },
    {
      "task_id": "requests_6589",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 5
      },
      "decisions": 33,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_13920",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 6
      },
      "decisions": 34,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3043",
      "resolved": true,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 2
      },
      "decisions": 18,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14419",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 8
      },
      "decisions": 18,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_15588",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 6,
        "successful_test": 2
      },
      "decisions": 24,
      "sticky_violation": false
    },
    {
      "task_id": "requests_7328",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 9
      },
      "decisions": 30,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_15763",
      "resolved": false,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 25,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3486",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 3
      },
      "decisions": 20,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14978",
      "resolved": null,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 2
      },
      "decisions": 27,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14964",
      "resolved": false,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 17,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14361",
      "resolved": true,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 7,
        "successful_test": 2
      },
      "decisions": 16,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14099",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 3
      },
      "decisions": 24,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14303",
      "resolved": true,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 15,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14262",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 6
      },
      "decisions": 29,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3469",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 10
      },
      "decisions": 40,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3105",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 8
      },
      "decisions": 15,
      "sticky_violation": false
    },
    {
      "task_id": "requests_6757",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 14
      },
      "decisions": 36,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3063",
      "resolved": false,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 12,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3675",
      "resolved": false,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 25,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_15023",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 7
      },
      "decisions": 28,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3006",
      "resolved": true,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "successful_test",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "successful_test": 1
      },
      "condition_true_requests": {
        "successful_test": 2
      },
      "decisions": 30,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14266",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 10
      },
      "decisions": 42,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14349",
      "resolved": true,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 4
      },
      "decisions": 20,
      "sticky_violation": false
    },
    {
      "task_id": "requests_7433",
      "resolved": false,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 29,
      "sticky_violation": false
    },
    {
      "task_id": "requests_7309",
      "resolved": false,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 31,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14077",
      "resolved": true,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "successful_test",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "successful_test": 1
      },
      "condition_true_requests": {
        "successful_test": 2
      },
      "decisions": 18,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3934",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 2
      },
      "decisions": 13,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14791",
      "resolved": true,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 17,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14512",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 3
      },
      "decisions": 26,
      "sticky_violation": false
    },
    {
      "task_id": "rich_4076",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "repeat",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "repeat": 1
      },
      "condition_true_requests": {
        "repeat": 1,
        "budget_240s": 6
      },
      "decisions": 30,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14986",
      "resolved": false,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 12,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14360",
      "resolved": false,
      "final_adapter": "rft_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {},
      "condition_true_requests": {},
      "decisions": 1,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_13207",
      "resolved": true,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 6
      },
      "decisions": 25,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3471",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 3
      },
      "decisions": 21,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3454",
      "resolved": true,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "successful_test",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "successful_test": 1
      },
      "condition_true_requests": {
        "successful_test": 1
      },
      "decisions": 29,
      "sticky_violation": false
    },
    {
      "task_id": "requests_7427",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 5
      },
      "decisions": 21,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14873",
      "resolved": true,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 5
      },
      "decisions": 25,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_9425",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 8
      },
      "decisions": 38,
      "sticky_violation": false
    },
    {
      "task_id": "requests_7502",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 11
      },
      "decisions": 43,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3518",
      "resolved": true,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 21,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14851",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 2
      },
      "decisions": 37,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3506",
      "resolved": false,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 7,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_9555",
      "resolved": true,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 16,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3777",
      "resolved": true,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 5
      },
      "decisions": 30,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3468",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 1
      },
      "decisions": 17,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_11194",
      "resolved": true,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 3
      },
      "decisions": 23,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14482",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 1
      },
      "decisions": 13,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3935",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 5,
        "repeat": 2
      },
      "decisions": 14,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_11355",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 9
      },
      "decisions": 19,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3772",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 2
      },
      "decisions": 22,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_15589",
      "resolved": false,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 10,
      "sticky_violation": false
    },
    {
      "task_id": "rich_3296",
      "resolved": false,
      "final_adapter": "dpo_lora",
      "first_sdpo_trigger": null,
      "transition_triggers": {
        "two_completed_exchanges": 1
      },
      "condition_true_requests": {},
      "decisions": 26,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_15800",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 6
      },
      "decisions": 19,
      "sticky_violation": false
    },
    {
      "task_id": "requests_7315",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 7
      },
      "decisions": 41,
      "sticky_violation": false
    },
    {
      "task_id": "rich_4075",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 3
      },
      "decisions": 50,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14605",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 10
      },
      "decisions": 50,
      "sticky_violation": false
    },
    {
      "task_id": "fastapi_14583",
      "resolved": false,
      "final_adapter": "sdpo_lora",
      "first_sdpo_trigger": "budget_240s",
      "transition_triggers": {
        "two_completed_exchanges": 1,
        "budget_240s": 1
      },
      "condition_true_requests": {
        "budget_240s": 6
      },
      "decisions": 16,
      "sticky_violation": false
    }
  ],
  "end_adapter_counts": {
    "sdpo_lora": 63,
    "dpo_lora": 20,
    "rft_lora": 1
  },
  "transition_trigger_counts": {
    "two_completed_exchanges": 82,
    "budget_240s": 56,
    "successful_test": 6,
    "repeat": 1
  },
  "yield_by_first_sdpo_trigger": {
    "budget_240s": {
      "tasks": 56,
      "verified_passes": 9,
      "unknowns": 3
    },
    "repeat": {
      "tasks": 1,
      "verified_passes": 0,
      "unknowns": 0
    },
    "successful_test": {
      "tasks": 6,
      "verified_passes": 5,
      "unknowns": 0
    },
    "never_sdpo": {
      "tasks": 21,
      "verified_passes": 7,
      "unknowns": 0
    }
  }
}
```

## Pooled124-task comparison — DESCRIPTIVE

| Arm | N | Passes | Yield [Wilson 95%] | Mean calls | Mean tokens | Calls/solve | Tokens/solve | Timeouts | No patch | Unknown |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| A0 | 124 | 23 | 18.55% [12.69, 26.30] | 19.68 | 187,251.99 | 106.09 | 1,009,532.48 | 85 | 34 | 9 |
| router | 124 | 30 | 24.19% [17.50, 32.43] | 22.02 | 198,138.62 | 91.00 | 818,972.97 | 88 | 36 | 6 |

## Replacements and execution anomalies

```json
{
  "replacements": [],
  "anomalies": [
    {
      "time": 1794837845.6805308,
      "event": "stopped",
      "scope": "initial_launch_only",
      "reason": "Initial background shell PID2944685 did not survive launcher exit; no supervisor, model or task started. Relaunched with nohup in a new session, PID2944910.",
      "completed": 0
    },
    {
      "arm": "A0",
      "task_id": "rich_3944",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3944/attempt-0/evaluation/tasks/rich_3944",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": false,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3944/attempt-0/evaluation/tasks/rich_3944/traces/trace_rich_3944.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 77561856,
      "agent_error": "Sandbox execution error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 32768 tokens. However, you requested 16384 output tokens and your prompt contains at least 16385 input tokens, for a total of at least 32769 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=16385) LiteLLM Retried: 5 times",
      "time": 1794839496.2022457,
      "calls": 13,
      "tokens": 131107,
      "llm_calls": 13,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3944",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3944/attempt-0/evaluation/tasks/rich_3944",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3944/attempt-0/evaluation/tasks/rich_3944/traces/trace_rich_3944.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 83668992,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794839096.5235956,
      "calls": 28,
      "tokens": 269841,
      "llm_calls": 28,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3930",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3930/attempt-0/evaluation/tasks/rich_3930",
      "resolved": null,
      "verification_status": "could_not_interpret",
      "agent_timeout": true,
      "patch_bytes": 2309,
      "test_exit_code": 2,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3930/attempt-0/evaluation/tasks/rich_3930/traces/trace_rich_3930.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 101601280,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794840621.8891957,
      "calls": 12,
      "tokens": 118633,
      "llm_calls": 12,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3930",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3930/attempt-0/evaluation/tasks/rich_3930",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3930/attempt-0/evaluation/tasks/rich_3930/traces/trace_rich_3930.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 87486464,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794841222.1767585,
      "calls": 11,
      "tokens": 97327,
      "llm_calls": 11,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14372",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14372/attempt-0/evaluation/tasks/fastapi_14372",
      "resolved": true,
      "verification_status": "passed",
      "agent_timeout": true,
      "patch_bytes": 1749,
      "test_exit_code": 0,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14372/attempt-0/evaluation/tasks/fastapi_14372/traces/trace_fastapi_14372.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 76128256,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794841695.011606,
      "calls": 26,
      "tokens": 246472,
      "llm_calls": 26,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14372",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14372/attempt-0/evaluation/tasks/fastapi_14372",
      "resolved": true,
      "verification_status": "passed",
      "agent_timeout": true,
      "patch_bytes": 1078,
      "test_exit_code": 0,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14372/attempt-0/evaluation/tasks/fastapi_14372/traces/trace_fastapi_14372.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 87871488,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794842182.9854546,
      "calls": 29,
      "tokens": 231874,
      "llm_calls": 29,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14371",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14371/attempt-0/evaluation/tasks/fastapi_14371",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 920,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14371/attempt-0/evaluation/tasks/fastapi_14371/traces/trace_fastapi_14371.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 91901952,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794843552.657353,
      "calls": 17,
      "tokens": 179917,
      "llm_calls": 17,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14371",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14371/attempt-0/evaluation/tasks/fastapi_14371",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14371/attempt-0/evaluation/tasks/fastapi_14371/traces/trace_fastapi_14371.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 81092608,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794844010.360203,
      "calls": 12,
      "tokens": 91866,
      "llm_calls": 12,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14458",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14458/attempt-0/evaluation/tasks/fastapi_14458",
      "resolved": true,
      "verification_status": "passed",
      "agent_timeout": true,
      "patch_bytes": 3321,
      "test_exit_code": 0,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14458/attempt-0/evaluation/tasks/fastapi_14458/traces/trace_fastapi_14458.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 94244864,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794844342.448168,
      "calls": 10,
      "tokens": 92374,
      "llm_calls": 10,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_15030",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_15030/attempt-0/evaluation/tasks/fastapi_15030",
      "resolved": null,
      "verification_status": "could_not_interpret",
      "agent_timeout": false,
      "patch_bytes": 1099,
      "test_exit_code": 2,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_15030/attempt-0/evaluation/tasks/fastapi_15030/traces/trace_fastapi_15030.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 87089152,
      "agent_error": null,
      "time": 1794846707.8675182,
      "calls": 12,
      "tokens": 147678,
      "llm_calls": 15,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_15030",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_15030/attempt-0/evaluation/tasks/fastapi_15030",
      "resolved": null,
      "verification_status": "could_not_interpret",
      "agent_timeout": false,
      "patch_bytes": 1035,
      "test_exit_code": 2,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_15030/attempt-0/evaluation/tasks/fastapi_15030/traces/trace_fastapi_15030.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 86528000,
      "agent_error": null,
      "time": 1794847174.8295467,
      "calls": 18,
      "tokens": 172670,
      "llm_calls": 21,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14962",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14962/attempt-0/evaluation/tasks/fastapi_14962",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14962/attempt-0/evaluation/tasks/fastapi_14962/traces/trace_fastapi_14962.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 82653184,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794847662.7436156,
      "calls": 15,
      "tokens": 138580,
      "llm_calls": 15,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14962",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14962/attempt-0/evaluation/tasks/fastapi_14962",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14962/attempt-0/evaluation/tasks/fastapi_14962/traces/trace_fastapi_14962.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 76083200,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794848129.537608,
      "calls": 37,
      "tokens": 313514,
      "llm_calls": 37,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_15280",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_15280/attempt-0/evaluation/tasks/fastapi_15280",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_15280/attempt-0/evaluation/tasks/fastapi_15280/traces/trace_fastapi_15280.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 50204672,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794849580.4263287,
      "calls": 32,
      "tokens": 320795,
      "llm_calls": 34,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_15280",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_15280/attempt-0/evaluation/tasks/fastapi_15280",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_15280/attempt-0/evaluation/tasks/fastapi_15280/traces/trace_fastapi_15280.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 63909888,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794849080.5655222,
      "calls": 35,
      "tokens": 364585,
      "llm_calls": 35,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "requests_7505",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/requests_7505/attempt-0/evaluation/tasks/requests_7505",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 1818,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/requests_7505/attempt-0/evaluation/tasks/requests_7505/traces/trace_requests_7505.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 94302208,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794849907.4744062,
      "calls": 29,
      "tokens": 242466,
      "llm_calls": 29,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "requests_7505",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/requests_7505/attempt-0/evaluation/tasks/requests_7505",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 2438,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/requests_7505/attempt-0/evaluation/tasks/requests_7505/traces/trace_requests_7505.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 90034176,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794850515.299347,
      "calls": 23,
      "tokens": 178472,
      "llm_calls": 24,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_4079",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_4079/attempt-0/evaluation/tasks/rich_4079",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_4079/attempt-0/evaluation/tasks/rich_4079/traces/trace_rich_4079.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 77766656,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794851048.777521,
      "calls": 46,
      "tokens": 456807,
      "llm_calls": 46,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_4079",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_4079/attempt-0/evaluation/tasks/rich_4079",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 321,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_4079/attempt-0/evaluation/tasks/rich_4079/traces/trace_rich_4079.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 83210240,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794851568.1842926,
      "calls": 44,
      "tokens": 405787,
      "llm_calls": 44,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3180",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3180/attempt-0/evaluation/tasks/rich_3180",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3180/attempt-0/evaluation/tasks/rich_3180/traces/trace_rich_3180.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 90927104,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794852065.1515484,
      "calls": 4,
      "tokens": 28927,
      "llm_calls": 6,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3180",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3180/attempt-0/evaluation/tasks/rich_3180",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3180/attempt-0/evaluation/tasks/rich_3180/traces/trace_rich_3180.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 90910720,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794852650.3176043,
      "calls": 5,
      "tokens": 30071,
      "llm_calls": 5,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14459",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14459/attempt-0/evaluation/tasks/fastapi_14459",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": false,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14459/attempt-0/evaluation/tasks/fastapi_14459/traces/trace_fastapi_14459.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 81088512,
      "agent_error": "Sandbox execution error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 32768 tokens. However, you requested 16384 output tokens and your prompt contains at least 16385 input tokens, for a total of at least 32769 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=16385) LiteLLM Retried: 5 times",
      "time": 1794853319.5146618,
      "calls": 7,
      "tokens": 68442,
      "llm_calls": 7,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14459",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14459/attempt-0/evaluation/tasks/fastapi_14459",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14459/attempt-0/evaluation/tasks/fastapi_14459/traces/trace_fastapi_14459.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 80924672,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794852967.2912915,
      "calls": 12,
      "tokens": 105821,
      "llm_calls": 12,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14186",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14186/attempt-0/evaluation/tasks/fastapi_14186",
      "resolved": null,
      "verification_status": "could_not_interpret",
      "agent_timeout": true,
      "patch_bytes": 711,
      "test_exit_code": 2,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14186/attempt-0/evaluation/tasks/fastapi_14186/traces/trace_fastapi_14186.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 81338368,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794854289.2699475,
      "calls": 8,
      "tokens": 85174,
      "llm_calls": 8,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14186",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14186/attempt-0/evaluation/tasks/fastapi_14186",
      "resolved": null,
      "verification_status": "could_not_interpret",
      "agent_timeout": true,
      "patch_bytes": 804,
      "test_exit_code": 2,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14186/attempt-0/evaluation/tasks/fastapi_14186/traces/trace_fastapi_14186.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 81293312,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794853816.69483,
      "calls": 11,
      "tokens": 94626,
      "llm_calls": 11,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3130",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3130/attempt-0/evaluation/tasks/rich_3130",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": false,
      "patch_bytes": 590,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3130/attempt-0/evaluation/tasks/rich_3130/traces/trace_rich_3130.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 93839360,
      "agent_error": "Sandbox execution error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 32768 tokens. However, you requested 16384 output tokens and your prompt contains at least 16385 input tokens, for a total of at least 32769 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=16385) LiteLLM Retried: 5 times",
      "time": 1794855161.961793,
      "calls": 20,
      "tokens": 204410,
      "llm_calls": 20,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3130",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3130/attempt-0/evaluation/tasks/rich_3130",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 1665,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3130/attempt-0/evaluation/tasks/rich_3130/traces/trace_rich_3130.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 100954112,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794854833.3940477,
      "calls": 32,
      "tokens": 274056,
      "llm_calls": 32,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14430",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14430/attempt-0/evaluation/tasks/fastapi_14430",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 1030,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14430/attempt-0/evaluation/tasks/fastapi_14430/traces/trace_fastapi_14430.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 86532096,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794855494.0766041,
      "calls": 13,
      "tokens": 95315,
      "llm_calls": 13,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14430",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14430/attempt-0/evaluation/tasks/fastapi_14430",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 2329,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14430/attempt-0/evaluation/tasks/fastapi_14430/traces/trace_fastapi_14430.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 73093120,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794855973.095233,
      "calls": 15,
      "tokens": 126303,
      "llm_calls": 15,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_13786",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_13786/attempt-0/evaluation/tasks/fastapi_13786",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 2431,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_13786/attempt-0/evaluation/tasks/fastapi_13786/traces/trace_fastapi_13786.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 92913664,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794856452.9427204,
      "calls": 17,
      "tokens": 174131,
      "llm_calls": 17,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_13786",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_13786/attempt-0/evaluation/tasks/fastapi_13786",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 3175,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_13786/attempt-0/evaluation/tasks/fastapi_13786/traces/trace_fastapi_13786.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 93544448,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794857035.3328571,
      "calls": 14,
      "tokens": 135804,
      "llm_calls": 14,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3942",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3942/attempt-0/evaluation/tasks/rich_3942",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3942/attempt-0/evaluation/tasks/rich_3942/traces/trace_rich_3942.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 87150592,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794858627.657741,
      "calls": 14,
      "tokens": 144240,
      "llm_calls": 14,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3942",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3942/attempt-0/evaluation/tasks/rich_3942",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3942/attempt-0/evaluation/tasks/rich_3942/traces/trace_rich_3942.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 60309504,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794858166.9167855,
      "calls": 13,
      "tokens": 133521,
      "llm_calls": 14,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_5077",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_5077/attempt-0/evaluation/tasks/fastapi_5077",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": false,
      "patch_bytes": 1237,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_5077/attempt-0/evaluation/tasks/fastapi_5077/traces/trace_fastapi_5077.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 86077440,
      "agent_error": "Sandbox execution error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 32768 tokens. However, you requested 16384 output tokens and your prompt contains at least 16385 input tokens, for a total of at least 32769 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=16385) LiteLLM Retried: 5 times",
      "time": 1794859519.183439,
      "calls": 12,
      "tokens": 115496,
      "llm_calls": 12,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_5077",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_5077/attempt-0/evaluation/tasks/fastapi_5077",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 1973,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_5077/attempt-0/evaluation/tasks/fastapi_5077/traces/trace_fastapi_5077.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 88010752,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794859105.134426,
      "calls": 30,
      "tokens": 252266,
      "llm_calls": 30,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14448",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14448/attempt-0/evaluation/tasks/fastapi_14448",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": false,
      "patch_bytes": 2907,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14448/attempt-0/evaluation/tasks/fastapi_14448/traces/trace_fastapi_14448.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 90796032,
      "agent_error": "Sandbox execution error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 32768 tokens. However, you requested 16384 output tokens and your prompt contains at least 16385 input tokens, for a total of at least 32769 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=16385) LiteLLM Retried: 5 times",
      "time": 1794859821.2194903,
      "calls": 8,
      "tokens": 68332,
      "llm_calls": 8,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14448",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14448/attempt-0/evaluation/tasks/fastapi_14448",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14448/attempt-0/evaluation/tasks/fastapi_14448/traces/trace_fastapi_14448.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 51879936,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794860288.933024,
      "calls": 19,
      "tokens": 112357,
      "llm_calls": 19,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14609",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14609/attempt-0/evaluation/tasks/fastapi_14609",
      "resolved": null,
      "verification_status": "could_not_interpret",
      "agent_timeout": true,
      "patch_bytes": 3248,
      "test_exit_code": 2,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14609/attempt-0/evaluation/tasks/fastapi_14609/traces/trace_fastapi_14609.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 80777216,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794861309.349398,
      "calls": 19,
      "tokens": 197565,
      "llm_calls": 19,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14609",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14609/attempt-0/evaluation/tasks/fastapi_14609",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14609/attempt-0/evaluation/tasks/fastapi_14609/traces/trace_fastapi_14609.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 65331200,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794861773.6734908,
      "calls": 18,
      "tokens": 173361,
      "llm_calls": 18,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "requests_6589",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/requests_6589/attempt-0/evaluation/tasks/requests_6589",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/requests_6589/attempt-0/evaluation/tasks/requests_6589/traces/trace_requests_6589.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 89313280,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794862562.0843549,
      "calls": 24,
      "tokens": 226233,
      "llm_calls": 24,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "requests_6589",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/requests_6589/attempt-0/evaluation/tasks/requests_6589",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 986,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/requests_6589/attempt-0/evaluation/tasks/requests_6589/traces/trace_requests_6589.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 93351936,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794862100.752802,
      "calls": 31,
      "tokens": 293589,
      "llm_calls": 31,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_13920",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_13920/attempt-0/evaluation/tasks/fastapi_13920",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_13920/attempt-0/evaluation/tasks/fastapi_13920/traces/trace_fastapi_13920.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 76156928,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794862879.0093858,
      "calls": 17,
      "tokens": 152803,
      "llm_calls": 17,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3043",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3043/attempt-0/evaluation/tasks/rich_3043",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 294,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3043/attempt-0/evaluation/tasks/rich_3043/traces/trace_rich_3043.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 101376000,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794863828.54865,
      "calls": 21,
      "tokens": 167745,
      "llm_calls": 21,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3043",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3043/attempt-0/evaluation/tasks/rich_3043",
      "resolved": true,
      "verification_status": "passed",
      "agent_timeout": true,
      "patch_bytes": 449,
      "test_exit_code": 0,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3043/attempt-0/evaluation/tasks/rich_3043/traces/trace_rich_3043.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 101101568,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794864299.9897413,
      "calls": 14,
      "tokens": 125781,
      "llm_calls": 16,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14419",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14419/attempt-0/evaluation/tasks/fastapi_14419",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 1602,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14419/attempt-0/evaluation/tasks/fastapi_14419/traces/trace_fastapi_14419.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 78434304,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794864779.5777638,
      "calls": 28,
      "tokens": 268625,
      "llm_calls": 28,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14419",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14419/attempt-0/evaluation/tasks/fastapi_14419",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14419/attempt-0/evaluation/tasks/fastapi_14419/traces/trace_fastapi_14419.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 66768896,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794865241.8389926,
      "calls": 25,
      "tokens": 220121,
      "llm_calls": 24,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "requests_7328",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/requests_7328/attempt-0/evaluation/tasks/requests_7328",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/requests_7328/attempt-0/evaluation/tasks/requests_7328/traces/trace_requests_7328.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 71675904,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794866940.9728858,
      "calls": 19,
      "tokens": 155471,
      "llm_calls": 19,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "requests_7328",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/requests_7328/attempt-0/evaluation/tasks/requests_7328",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 3009,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/requests_7328/attempt-0/evaluation/tasks/requests_7328/traces/trace_requests_7328.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 93937664,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794866478.5925286,
      "calls": 27,
      "tokens": 268817,
      "llm_calls": 28,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_15763",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_15763/attempt-0/evaluation/tasks/fastapi_15763",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 3718,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_15763/attempt-0/evaluation/tasks/fastapi_15763/traces/trace_fastapi_15763.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 87343104,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794867904.438047,
      "calls": 42,
      "tokens": 418729,
      "llm_calls": 43,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3486",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3486/attempt-0/evaluation/tasks/rich_3486",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3486/attempt-0/evaluation/tasks/rich_3486/traces/trace_rich_3486.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 90828800,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794868866.2147298,
      "calls": 19,
      "tokens": 184435,
      "llm_calls": 19,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3486",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3486/attempt-0/evaluation/tasks/rich_3486",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3486/attempt-0/evaluation/tasks/rich_3486/traces/trace_rich_3486.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 90341376,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794868365.7141755,
      "calls": 18,
      "tokens": 157223,
      "llm_calls": 18,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14978",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14978/attempt-0/evaluation/tasks/fastapi_14978",
      "resolved": null,
      "verification_status": "could_not_interpret",
      "agent_timeout": false,
      "patch_bytes": 3099,
      "test_exit_code": 2,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14978/attempt-0/evaluation/tasks/fastapi_14978/traces/trace_fastapi_14978.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 87744512,
      "agent_error": "Sandbox execution error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 32768 tokens. However, you requested 16384 output tokens and your prompt contains at least 16385 input tokens, for a total of at least 32769 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=16385) LiteLLM Retried: 5 times",
      "time": 1794869153.071942,
      "calls": 21,
      "tokens": 182605,
      "llm_calls": 21,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14978",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14978/attempt-0/evaluation/tasks/fastapi_14978",
      "resolved": null,
      "verification_status": "could_not_interpret",
      "agent_timeout": true,
      "patch_bytes": 856,
      "test_exit_code": 2,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14978/attempt-0/evaluation/tasks/fastapi_14978/traces/trace_fastapi_14978.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 86618112,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794869771.7669282,
      "calls": 35,
      "tokens": 305854,
      "llm_calls": 35,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14099",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14099/attempt-0/evaluation/tasks/fastapi_14099",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14099/attempt-0/evaluation/tasks/fastapi_14099/traces/trace_fastapi_14099.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 50708480,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794872230.3520436,
      "calls": 31,
      "tokens": 292396,
      "llm_calls": 31,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14099",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14099/attempt-0/evaluation/tasks/fastapi_14099",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14099/attempt-0/evaluation/tasks/fastapi_14099/traces/trace_fastapi_14099.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 53891072,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794871772.3842852,
      "calls": 35,
      "tokens": 287404,
      "llm_calls": 34,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14303",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14303/attempt-0/evaluation/tasks/fastapi_14303",
      "resolved": true,
      "verification_status": "passed",
      "agent_timeout": true,
      "patch_bytes": 745,
      "test_exit_code": 0,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14303/attempt-0/evaluation/tasks/fastapi_14303/traces/trace_fastapi_14303.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 79790080,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794872562.4434955,
      "calls": 29,
      "tokens": 264721,
      "llm_calls": 29,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14262",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14262/attempt-0/evaluation/tasks/fastapi_14262",
      "resolved": null,
      "verification_status": "could_not_interpret",
      "agent_timeout": true,
      "patch_bytes": 1711,
      "test_exit_code": 2,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14262/attempt-0/evaluation/tasks/fastapi_14262/traces/trace_fastapi_14262.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 87896064,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794873401.7756891,
      "calls": 27,
      "tokens": 274763,
      "llm_calls": 27,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14262",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14262/attempt-0/evaluation/tasks/fastapi_14262",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14262/attempt-0/evaluation/tasks/fastapi_14262/traces/trace_fastapi_14262.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 63471616,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794873857.5712097,
      "calls": 26,
      "tokens": 236904,
      "llm_calls": 26,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3469",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3469/attempt-0/evaluation/tasks/rich_3469",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 902,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3469/attempt-0/evaluation/tasks/rich_3469/traces/trace_rich_3469.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 90951680,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794874656.27295,
      "calls": 23,
      "tokens": 203274,
      "llm_calls": 23,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3469",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3469/attempt-0/evaluation/tasks/rich_3469",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 512,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3469/attempt-0/evaluation/tasks/rich_3469/traces/trace_rich_3469.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 77606912,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794874184.6268275,
      "calls": 46,
      "tokens": 386715,
      "llm_calls": 44,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3105",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3105/attempt-0/evaluation/tasks/rich_3105",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": false,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3105/attempt-0/evaluation/tasks/rich_3105/traces/trace_rich_3105.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 90357760,
      "agent_error": "Sandbox execution error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 32768 tokens. However, you requested 16384 output tokens and your prompt contains at least 16385 input tokens, for a total of at least 32769 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=16385) LiteLLM Retried: 5 times",
      "time": 1794875523.2246678,
      "calls": 27,
      "tokens": 238713,
      "llm_calls": 27,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3105",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3105/attempt-0/evaluation/tasks/rich_3105",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3105/attempt-0/evaluation/tasks/rich_3105/traces/trace_rich_3105.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 90451968,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794875120.5254421,
      "calls": 22,
      "tokens": 164755,
      "llm_calls": 24,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "requests_6757",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/requests_6757/attempt-0/evaluation/tasks/requests_6757",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/requests_6757/attempt-0/evaluation/tasks/requests_6757/traces/trace_requests_6757.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 88035328,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794876445.495209,
      "calls": 22,
      "tokens": 287266,
      "llm_calls": 29,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "requests_6757",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/requests_6757/attempt-0/evaluation/tasks/requests_6757",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/requests_6757/attempt-0/evaluation/tasks/requests_6757/traces/trace_requests_6757.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 76046336,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794875984.5060039,
      "calls": 25,
      "tokens": 381391,
      "llm_calls": 35,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3063",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3063/attempt-0/evaluation/tasks/rich_3063",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 3402,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3063/attempt-0/evaluation/tasks/rich_3063/traces/trace_rich_3063.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 80773120,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794877599.8883624,
      "calls": 18,
      "tokens": 149503,
      "llm_calls": 18,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3063",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3063/attempt-0/evaluation/tasks/rich_3063",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 670,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3063/attempt-0/evaluation/tasks/rich_3063/traces/trace_rich_3063.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 90873856,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794877056.3689802,
      "calls": 11,
      "tokens": 79491,
      "llm_calls": 11,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_15023",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_15023/attempt-0/evaluation/tasks/fastapi_15023",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 3622,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_15023/attempt-0/evaluation/tasks/fastapi_15023/traces/trace_fastapi_15023.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 81076224,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794878792.2757168,
      "calls": 32,
      "tokens": 331246,
      "llm_calls": 33,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_15023",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_15023/attempt-0/evaluation/tasks/fastapi_15023",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_15023/attempt-0/evaluation/tasks/fastapi_15023/traces/trace_fastapi_15023.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 65728512,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794879252.9923184,
      "calls": 25,
      "tokens": 207866,
      "llm_calls": 26,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14266",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14266/attempt-0/evaluation/tasks/fastapi_14266",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14266/attempt-0/evaluation/tasks/fastapi_14266/traces/trace_fastapi_14266.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 61128704,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794880970.5613334,
      "calls": 45,
      "tokens": 449405,
      "llm_calls": 45,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14266",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14266/attempt-0/evaluation/tasks/fastapi_14266",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": false,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14266/attempt-0/evaluation/tasks/fastapi_14266/traces/trace_fastapi_14266.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 61743104,
      "agent_error": "Agent exceeded turns budget (50 turns)",
      "time": 1794880436.9575942,
      "calls": 50,
      "tokens": 427639,
      "llm_calls": 50,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14349",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14349/attempt-0/evaluation/tasks/fastapi_14349",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 1163,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14349/attempt-0/evaluation/tasks/fastapi_14349/traces/trace_fastapi_14349.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 81154048,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794881302.6358466,
      "calls": 13,
      "tokens": 100616,
      "llm_calls": 13,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14349",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14349/attempt-0/evaluation/tasks/fastapi_14349",
      "resolved": true,
      "verification_status": "passed",
      "agent_timeout": true,
      "patch_bytes": 2657,
      "test_exit_code": 0,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14349/attempt-0/evaluation/tasks/fastapi_14349/traces/trace_fastapi_14349.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 77406208,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794881778.5993984,
      "calls": 17,
      "tokens": 163466,
      "llm_calls": 17,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3934",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3934/attempt-0/evaluation/tasks/rich_3934",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 418,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3934/attempt-0/evaluation/tasks/rich_3934/traces/trace_rich_3934.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 71135232,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794884069.8010733,
      "calls": 14,
      "tokens": 113888,
      "llm_calls": 14,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3934",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3934/attempt-0/evaluation/tasks/rich_3934",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3934/attempt-0/evaluation/tasks/rich_3934/traces/trace_rich_3934.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 60018688,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794884530.9037762,
      "calls": 12,
      "tokens": 108620,
      "llm_calls": 12,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14791",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14791/attempt-0/evaluation/tasks/fastapi_14791",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 793,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14791/attempt-0/evaluation/tasks/fastapi_14791/traces/trace_fastapi_14791.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 97980416,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794885004.1195602,
      "calls": 22,
      "tokens": 226303,
      "llm_calls": 22,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14512",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14512/attempt-0/evaluation/tasks/fastapi_14512",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 8428,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14512/attempt-0/evaluation/tasks/fastapi_14512/traces/trace_fastapi_14512.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 88485888,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794886179.7393951,
      "calls": 34,
      "tokens": 345798,
      "llm_calls": 34,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14512",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14512/attempt-0/evaluation/tasks/fastapi_14512",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 3112,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14512/attempt-0/evaluation/tasks/fastapi_14512/traces/trace_fastapi_14512.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 88576000,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794885706.592135,
      "calls": 22,
      "tokens": 184042,
      "llm_calls": 24,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_4076",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_4076/attempt-0/evaluation/tasks/rich_4076",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 367,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_4076/attempt-0/evaluation/tasks/rich_4076/traces/trace_rich_4076.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 86978560,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794887167.5203319,
      "calls": 37,
      "tokens": 358579,
      "llm_calls": 37,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_4076",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_4076/attempt-0/evaluation/tasks/rich_4076",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 879,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_4076/attempt-0/evaluation/tasks/rich_4076/traces/trace_rich_4076.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 94773248,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794886657.2179184,
      "calls": 37,
      "tokens": 289077,
      "llm_calls": 38,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14986",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14986/attempt-0/evaluation/tasks/fastapi_14986",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 1047,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14986/attempt-0/evaluation/tasks/fastapi_14986/traces/trace_fastapi_14986.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 74846208,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794887904.9280434,
      "calls": 11,
      "tokens": 84617,
      "llm_calls": 11,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14360",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14360/attempt-0/evaluation/tasks/fastapi_14360",
      "resolved": true,
      "verification_status": "passed",
      "agent_timeout": true,
      "patch_bytes": 4680,
      "test_exit_code": 0,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14360/attempt-0/evaluation/tasks/fastapi_14360/traces/trace_fastapi_14360.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 81010688,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794888698.1563838,
      "calls": 12,
      "tokens": 118077,
      "llm_calls": 12,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14360",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14360/attempt-0/evaluation/tasks/fastapi_14360",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14360/attempt-0/evaluation/tasks/fastapi_14360/traces/trace_fastapi_14360.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 81055744,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794888221.8837814,
      "calls": 6,
      "tokens": 36031,
      "llm_calls": 6,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_13207",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_13207/attempt-0/evaluation/tasks/fastapi_13207",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 3445,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_13207/attempt-0/evaluation/tasks/fastapi_13207/traces/trace_fastapi_13207.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 81240064,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794889030.2418346,
      "calls": 21,
      "tokens": 217697,
      "llm_calls": 21,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_13207",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_13207/attempt-0/evaluation/tasks/fastapi_13207",
      "resolved": true,
      "verification_status": "passed",
      "agent_timeout": true,
      "patch_bytes": 3113,
      "test_exit_code": 0,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_13207/attempt-0/evaluation/tasks/fastapi_13207/traces/trace_fastapi_13207.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 79470592,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794889506.6430156,
      "calls": 23,
      "tokens": 207822,
      "llm_calls": 23,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3471",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3471/attempt-0/evaluation/tasks/rich_3471",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 834,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3471/attempt-0/evaluation/tasks/rich_3471/traces/trace_rich_3471.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 91385856,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794890436.466475,
      "calls": 19,
      "tokens": 165817,
      "llm_calls": 19,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "requests_7427",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/requests_7427/attempt-0/evaluation/tasks/requests_7427",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 3052,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/requests_7427/attempt-0/evaluation/tasks/requests_7427/traces/trace_requests_7427.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 94191616,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794891979.1167636,
      "calls": 23,
      "tokens": 215197,
      "llm_calls": 23,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "requests_7427",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/requests_7427/attempt-0/evaluation/tasks/requests_7427",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 2405,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/requests_7427/attempt-0/evaluation/tasks/requests_7427/traces/trace_requests_7427.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 94580736,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794891511.165682,
      "calls": 19,
      "tokens": 141453,
      "llm_calls": 19,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14873",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14873/attempt-0/evaluation/tasks/fastapi_14873",
      "resolved": true,
      "verification_status": "passed",
      "agent_timeout": true,
      "patch_bytes": 5240,
      "test_exit_code": 0,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14873/attempt-0/evaluation/tasks/fastapi_14873/traces/trace_fastapi_14873.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 76242944,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794892311.1444075,
      "calls": 38,
      "tokens": 349066,
      "llm_calls": 38,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_9425",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_9425/attempt-0/evaluation/tasks/fastapi_9425",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 746,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_9425/attempt-0/evaluation/tasks/fastapi_9425/traces/trace_fastapi_9425.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 75296768,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794893079.2788725,
      "calls": 46,
      "tokens": 321374,
      "llm_calls": 46,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "requests_7502",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/requests_7502/attempt-0/evaluation/tasks/requests_7502",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": false,
      "patch_bytes": 2265,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/requests_7502/attempt-0/evaluation/tasks/requests_7502/traces/trace_requests_7502.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 94089216,
      "agent_error": "Sandbox execution error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 32768 tokens. However, you requested 16384 output tokens and your prompt contains at least 16385 input tokens, for a total of at least 32769 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=16385) LiteLLM Retried: 5 times",
      "time": 1794894375.7496223,
      "calls": 26,
      "tokens": 243053,
      "llm_calls": 26,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "requests_7502",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/requests_7502/attempt-0/evaluation/tasks/requests_7502",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 4461,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/requests_7502/attempt-0/evaluation/tasks/requests_7502/traces/trace_requests_7502.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 92172288,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794894059.0936396,
      "calls": 40,
      "tokens": 331961,
      "llm_calls": 41,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14851",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14851/attempt-0/evaluation/tasks/fastapi_14851",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14851/attempt-0/evaluation/tasks/fastapi_14851/traces/trace_fastapi_14851.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 80920576,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794895991.3556798,
      "calls": 49,
      "tokens": 477965,
      "llm_calls": 49,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14851",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14851/attempt-0/evaluation/tasks/fastapi_14851",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14851/attempt-0/evaluation/tasks/fastapi_14851/traces/trace_fastapi_14851.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 81039360,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794895457.2165408,
      "calls": 34,
      "tokens": 299733,
      "llm_calls": 35,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3506",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3506/attempt-0/evaluation/tasks/rich_3506",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3506/attempt-0/evaluation/tasks/rich_3506/traces/trace_rich_3506.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 78077952,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794896308.2909045,
      "calls": 2,
      "tokens": 12986,
      "llm_calls": 2,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3506",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3506/attempt-0/evaluation/tasks/rich_3506",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 1116,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3506/attempt-0/evaluation/tasks/rich_3506/traces/trace_rich_3506.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 101371904,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794896779.3001852,
      "calls": 6,
      "tokens": 40703,
      "llm_calls": 6,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3777",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3777/attempt-0/evaluation/tasks/rich_3777",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3777/attempt-0/evaluation/tasks/rich_3777/traces/trace_rich_3777.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 87461888,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794897765.5592382,
      "calls": 39,
      "tokens": 330841,
      "llm_calls": 39,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3777",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3777/attempt-0/evaluation/tasks/rich_3777",
      "resolved": true,
      "verification_status": "passed",
      "agent_timeout": true,
      "patch_bytes": 1524,
      "test_exit_code": 0,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3777/attempt-0/evaluation/tasks/rich_3777/traces/trace_rich_3777.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 101007360,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794898306.3080394,
      "calls": 27,
      "tokens": 260772,
      "llm_calls": 28,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3468",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3468/attempt-0/evaluation/tasks/rich_3468",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 7105,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3468/attempt-0/evaluation/tasks/rich_3468/traces/trace_rich_3468.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 90812416,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794899115.060156,
      "calls": 18,
      "tokens": 166746,
      "llm_calls": 18,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3468",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3468/attempt-0/evaluation/tasks/rich_3468",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 6841,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3468/attempt-0/evaluation/tasks/rich_3468/traces/trace_rich_3468.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 90816512,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794898638.3815231,
      "calls": 16,
      "tokens": 127243,
      "llm_calls": 16,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_11194",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_11194/attempt-0/evaluation/tasks/fastapi_11194",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 4681,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_11194/attempt-0/evaluation/tasks/fastapi_11194/traces/trace_fastapi_11194.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 81100800,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794900143.1392148,
      "calls": 26,
      "tokens": 213811,
      "llm_calls": 26,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_11194",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_11194/attempt-0/evaluation/tasks/fastapi_11194",
      "resolved": true,
      "verification_status": "passed",
      "agent_timeout": true,
      "patch_bytes": 1978,
      "test_exit_code": 0,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_11194/attempt-0/evaluation/tasks/fastapi_11194/traces/trace_fastapi_11194.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 80969728,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794899591.466033,
      "calls": 21,
      "tokens": 179647,
      "llm_calls": 21,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14482",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14482/attempt-0/evaluation/tasks/fastapi_14482",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 1815,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14482/attempt-0/evaluation/tasks/fastapi_14482/traces/trace_fastapi_14482.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 94896128,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794901092.7808223,
      "calls": 26,
      "tokens": 251622,
      "llm_calls": 26,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14482",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14482/attempt-0/evaluation/tasks/fastapi_14482",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 712,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14482/attempt-0/evaluation/tasks/fastapi_14482/traces/trace_fastapi_14482.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 93339648,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794900619.5286047,
      "calls": 21,
      "tokens": 179538,
      "llm_calls": 21,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3935",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3935/attempt-0/evaluation/tasks/rich_3935",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 3132,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3935/attempt-0/evaluation/tasks/rich_3935/traces/trace_rich_3935.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 101097472,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794902153.2723954,
      "calls": 15,
      "tokens": 130962,
      "llm_calls": 15,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3935",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3935/attempt-0/evaluation/tasks/rich_3935",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 997,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3935/attempt-0/evaluation/tasks/rich_3935/traces/trace_rich_3935.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 78708736,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794901686.0744197,
      "calls": 13,
      "tokens": 128320,
      "llm_calls": 13,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_11355",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_11355/attempt-0/evaluation/tasks/fastapi_11355",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 738,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_11355/attempt-0/evaluation/tasks/fastapi_11355/traces/trace_fastapi_11355.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 71184384,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794902480.140361,
      "calls": 26,
      "tokens": 199997,
      "llm_calls": 26,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_11355",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_11355/attempt-0/evaluation/tasks/fastapi_11355",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_11355/attempt-0/evaluation/tasks/fastapi_11355/traces/trace_fastapi_11355.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 64606208,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794902913.7330117,
      "calls": 31,
      "tokens": 197604,
      "llm_calls": 31,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_3772",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3772/attempt-0/evaluation/tasks/rich_3772",
      "resolved": null,
      "verification_status": "could_not_interpret",
      "agent_timeout": true,
      "patch_bytes": 1282,
      "test_exit_code": 124,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_3772/attempt-0/evaluation/tasks/rich_3772/traces/trace_rich_3772.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 1296859136,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794903728.331666,
      "calls": 23,
      "tokens": 215263,
      "llm_calls": 23,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_3772",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3772/attempt-0/evaluation/tasks/rich_3772",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_3772/attempt-0/evaluation/tasks/rich_3772/traces/trace_rich_3772.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 63156224,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794903230.4517758,
      "calls": 19,
      "tokens": 167862,
      "llm_calls": 20,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_15589",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_15589/attempt-0/evaluation/tasks/fastapi_15589",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 3968,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_15589/attempt-0/evaluation/tasks/fastapi_15589/traces/trace_fastapi_15589.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 80805888,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794904060.2978475,
      "calls": 22,
      "tokens": 205416,
      "llm_calls": 22,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_15589",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_15589/attempt-0/evaluation/tasks/fastapi_15589",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_15589/attempt-0/evaluation/tasks/fastapi_15589/traces/trace_fastapi_15589.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 74354688,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794904500.576618,
      "calls": 9,
      "tokens": 84210,
      "llm_calls": 9,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_15800",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_15800/attempt-0/evaluation/tasks/fastapi_15800",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 1725,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_15800/attempt-0/evaluation/tasks/fastapi_15800/traces/trace_fastapi_15800.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 79646720,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794906042.525605,
      "calls": 38,
      "tokens": 368727,
      "llm_calls": 37,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_15800",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_15800/attempt-0/evaluation/tasks/fastapi_15800",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": true,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_15800/attempt-0/evaluation/tasks/fastapi_15800/traces/trace_fastapi_15800.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 64987136,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794905602.2726114,
      "calls": 27,
      "tokens": 204039,
      "llm_calls": 25,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "requests_7315",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/requests_7315/attempt-0/evaluation/tasks/requests_7315",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 2778,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/requests_7315/attempt-0/evaluation/tasks/requests_7315/traces/trace_requests_7315.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 94015488,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794906364.2927542,
      "calls": 45,
      "tokens": 428986,
      "llm_calls": 46,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "requests_7315",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/requests_7315/attempt-0/evaluation/tasks/requests_7315",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 2971,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/requests_7315/attempt-0/evaluation/tasks/requests_7315/traces/trace_requests_7315.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 89972736,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794906804.6574304,
      "calls": 39,
      "tokens": 334510,
      "llm_calls": 39,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "rich_4075",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_4075/attempt-0/evaluation/tasks/rich_4075",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 248,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/rich_4075/attempt-0/evaluation/tasks/rich_4075/traces/trace_rich_4075.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 95657984,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794907566.668628,
      "calls": 36,
      "tokens": 306748,
      "llm_calls": 36,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "rich_4075",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_4075/attempt-0/evaluation/tasks/rich_4075",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 1090,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/rich_4075/attempt-0/evaluation/tasks/rich_4075/traces/trace_rich_4075.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 91533312,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794907126.434488,
      "calls": 48,
      "tokens": 393283,
      "llm_calls": 48,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14605",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14605/attempt-0/evaluation/tasks/fastapi_14605",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 1971,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14605/attempt-0/evaluation/tasks/fastapi_14605/traces/trace_fastapi_14605.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 81154048,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794908321.2820055,
      "calls": 48,
      "tokens": 549907,
      "llm_calls": 49,
      "trace_missing": false
    },
    {
      "arm": "A0",
      "task_id": "fastapi_14583",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14583/attempt-0/evaluation/tasks/fastapi_14583",
      "resolved": false,
      "verification_status": "no_patch",
      "agent_timeout": false,
      "patch_bytes": 0,
      "test_exit_code": -1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/A0/fastapi_14583/attempt-0/evaluation/tasks/fastapi_14583/traces/trace_fastapi_14583.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 17448960,
      "agent_error": "Sandbox execution error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 32768 tokens. However, you requested 16384 output tokens and your prompt contains at least 16385 input tokens, for a total of at least 32769 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=16385) LiteLLM Retried: 5 times",
      "time": 1794909029.7405958,
      "calls": 6,
      "tokens": 57325,
      "llm_calls": 6,
      "trace_missing": false
    },
    {
      "arm": "router",
      "task_id": "fastapi_14583",
      "result_dir": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14583/attempt-0/evaluation/tasks/fastapi_14583",
      "resolved": false,
      "verification_status": "failed",
      "agent_timeout": true,
      "patch_bytes": 353,
      "test_exit_code": 1,
      "trace_path": "/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/results/confirmatory/router/fastapi_14583/attempt-0/evaluation/tasks/fastapi_14583/traces/trace_fastapi_14583.json",
      "cleanup_ok": true,
      "monitor_ok": true,
      "peak_observed_container_rss_bytes": 83238912,
      "agent_error": "Agent exceeded session timeout (5 min)",
      "time": 1794908648.2284677,
      "calls": 14,
      "tokens": 151755,
      "llm_calls": 14,
      "trace_missing": false
    }
  ]
}
```

Phase 2 DPO has not been authorized or run.
