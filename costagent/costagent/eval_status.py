"""Interpret one Docker agent outcome without hiding verification failures."""

from __future__ import annotations


def interpret_outcome(outcome: dict, monitor: dict, worker_returncode: int) -> tuple[bool | None, str]:
    """Return (resolved, verification_status); None means correctness is unknown.

    Agent timeouts with no patch are model failures. A verification error that
    differs from the agent's own error is an infrastructure/grading failure.
    The supervisor must have completed and cleaned up its owned containers.
    """
    if monitor.get("remaining_owned_ids"):
        raise RuntimeError("Owned evaluation containers remain after cleanup")
    if monitor.get("timed_out") or monitor.get("interrupted"):
        return None, "supervisor_incomplete"
    if worker_returncode not in (0, 1):
        return None, "worker_error"

    verification_error = outcome.get("verification_error")
    agent_error = outcome.get("agent_error")
    if verification_error and verification_error != agent_error:
        return None, "verification_error"

    test_exit = outcome.get("test_exit_code")
    resolved = outcome.get("resolved")
    if resolved is True and test_exit == 0 and worker_returncode == 0:
        return True, "passed"
    if resolved is False and test_exit == 1 and worker_returncode == 1:
        return False, "failed"
    if resolved is False and test_exit in (-1, None) and not outcome.get("patch_bytes"):
        return False, "no_patch"
    return None, "could_not_interpret"
