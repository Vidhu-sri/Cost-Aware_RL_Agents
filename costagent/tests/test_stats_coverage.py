import pytest

from costagent.stats import complete_case_tasks, ensure_complete_coverage


def test_complete_paired_coverage_passes():
    ensure_complete_coverage({"A0": {"t1": (), "t2": ()},
                              "A2": {"t1": (), "t2": ()}}, ["t1", "t2"])


def test_missing_task_blocks_inference_with_id():
    with pytest.raises(ValueError, match=r"A2: 1 missing \(t2\)"):
        ensure_complete_coverage({"A0": {"t1": (), "t2": ()},
                                  "A2": {"t1": ()}}, ["t1", "t2"])


def test_complete_cases_exclude_unknown_outcomes_without_marking_failure():
    tasks, excluded = complete_case_tasks(
        {"A0": {"t1": (), "t2": (), "t3": ()},
         "A2": {"t1": (), "t3": ()},
         "DPO": {"t1": (), "t2": ()}}, ["t1", "t2", "t3"])
    assert tasks == ["t1"]
    assert excluded == {"t2": ["A2"], "t3": ["DPO"]}
