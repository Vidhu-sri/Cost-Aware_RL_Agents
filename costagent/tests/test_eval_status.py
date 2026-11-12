import pytest

from costagent.eval_status import interpret_outcome


def monitor(**overrides):
    return {"remaining_owned_ids": [], "timed_out": False, "interrupted": False, **overrides}


@pytest.mark.parametrize("outcome,code,expected", [
    ({"resolved": True, "test_exit_code": 0}, 0, (True, "passed")),
    ({"resolved": False, "test_exit_code": 1}, 1, (False, "failed")),
    ({"resolved": False, "test_exit_code": -1, "patch_bytes": 0,
      "agent_error": "Agent exceeded session timeout", "verification_error": "Agent exceeded session timeout"},
     1, (False, "no_patch")),
    ({"resolved": False, "test_exit_code": -1, "patch_bytes": 130,
      "agent_error": "Agent exceeded session timeout", "verification_error": "git not found"},
     1, (None, "verification_error")),
    ({"resolved": False, "test_exit_code": 2, "patch_bytes": 130},
     1, (None, "could_not_interpret")),
])
def test_interpret_outcome(outcome, code, expected):
    assert interpret_outcome(outcome, monitor(), code) == expected


def test_supervisor_timeout_is_unknown():
    outcome = {"resolved": False, "test_exit_code": 1}
    assert interpret_outcome(outcome, monitor(timed_out=True), 124) == (None, "supervisor_incomplete")


def test_cleanup_failure_stops_batch():
    with pytest.raises(RuntimeError, match="containers remain"):
        interpret_outcome({}, monitor(remaining_owned_ids=["owned-container"]), 1)
