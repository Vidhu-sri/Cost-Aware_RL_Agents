# V2 smoke-gate deviations before any non-smoke attempt

The first `fastapi_14246` A0 smoke attempt, saved under
`attempts/smoke-v2-fastapi_14246/A0/`, exposed a guard implementation bug.
At the legitimate 300-second agent deadline, model telemetry tried to extend
an already-expiring `asyncio.Timeout` by 0.007 seconds and raised
`Cannot change state of expiring Timeout`. The controller stopped before any
non-smoke attempt. Its final snapshot matched the extracted 2,260-byte patch;
the task container and owned vLLM process cleaned up. The guard now records
post-expiry telemetry overhead without attempting to reschedule an expired
deadline. A focused regression test covers that state. The smoke was retried
under the separate `smoke-v2-retry1-` label; the original files were preserved.

The retried A0 smoke reached the wall deadline with a nonempty patch and a
matching final snapshot. Its final HTTP request was canceled at the deadline:
request 22 has `CancelledError`, no response file/status, and therefore no
vLLM usage. The inherited smoke validator rejected any missing usage, including
this expected canceled-request case. Before any non-smoke attempt, the v2 gate
was narrowed to accept missing usage **only** for a recorded agent wall timeout
with a canceled, response-less request. Missing usage on a completed response
or any other error remains fatal. Every outgoing request, including canceled
ones, must still pass the HTTP thinking-parameter guard. This clarification is
reported as a deviation from the original smoke telemetry wording; no token
count is invented for the canceled request.
