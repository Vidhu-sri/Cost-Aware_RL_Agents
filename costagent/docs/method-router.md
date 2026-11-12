# RFT / DPO / SDPO routing, method-v1-sticky

This experiment adds actual per-request adapter choice to the phase-v2 controller.
It is a hand-written policy; no learned gate or proven adapter specialization.
It does not merge weights, add a model call, or use evaluation labels to choose adapters.
The analyzer continues to use the original tool_lora. One base server serves all adapters.

## Exact policy

Start with RFT (A2). Switch to DPO after two completed non-free tool exchanges
(assistant call + matching tool response, excluding get_status and submit_patch).
Count exchanges by unique tool-call ID; keep state across context compaction.
Once any SDPO trigger fires, SDPO remains selected until the run ends.
The priority is sticky SDPO > elapsed time >= 240 s > repeat > successful test > DPO threshold > RFT.
A failed command does not override any SDPO trigger or sticky state.
Early SDPO triggers can skip DPO; there are at most two adapter switches.

Repeat means the last two completed non-free exchanges are both run_command,
with byte-identical command strings and identical SHA256 of JSON([stdout,stderr]).
No whitespace normalization. Missing stdout/stderr cannot establish a repeat.
Successful test means an integer exit_code of zero from a conservatively recognized
pytest, py.test, tox, or python[version] -m pytest/unittest invocation, optionally
prefixed with cd DIR &&. Pipelines, shell substitutions and compound commands are
not accepted as evidence. Generic command success is not test success.
This local test trigger is not a verified task solve; only official verification sets resolved.
Budget means 240 monotonic seconds from the installed harness's start_agent_session callback,
excluding Docker provisioning. The trigger acts at the next model request;
it does not interrupt an in-flight model request. No 80-call adapter trigger.

The original phase controller separately retains its tool masks, thinking flag,
output caps and 240-second/85-call submission phase. Its empty-tool fallback is
retained. Thus results evaluate the COMBINED adapter router and phase controller,
not adapter routing in isolation. Identical HTTP retries retain the same routing
and phase decision; they do not consume additional router turns.

## Evidence and operation

method_router.py composes PhaseRouter and changes the outgoing model field.
Tests exercise actual HTTP bodies using httpx.MockTransport, all adapters,
priority, retries, sticky state, compacted history and exact output matching.
serve_local.sh opts into three additional named adapters via COSTAGENT_METHOD_ROUTER=1.
The normal serving command remains unchanged when this flag is absent.
run_method_router40.py hashes adapter config/weights and both router sources,
checks served adapter paths, probes all three, and runs the original matched
40 IDs in sorted order, seed 42, temperature .2, 5 minutes / 100 tools,
900-second worker deadline, concurrency one, GPU fraction .60 / max sequences 1.
The batch preserves independent outcomes, raw model I/O, routing decisions,
verification output, monitor records and checkpointed summary.json.
All image/task setup and grading remain with the installed harness.
RSS is observed (not a cgroup cap); >12 GiB or monitoring failure stops this mode.
The batch final sweep touches only labels in its own recorded run manifests;
server shutdown runs even if that sweep raises an error.

Sources for architecture, not evidence of this heuristic's effectiveness:
https://docs.langchain.com/oss/python/langchain/models#dynamic-model-selection
https://docs.vllm.ai/en/latest/features/lora/#serving-lora-adapters

The existing developer-track submission.zip is not changed by this experiment.

## Monitoring repair and continuation, 2026-11-10

The first batch stopped on fastapi_14258 after an unreadable RSS sample. The old
sampler wrapped all member memory reads in one try block: a single process exit
could discard the whole sample. Its exception type was not saved, so the exact
original syscall failure cannot be reconstructed.
The repaired sampler skips exited processes individually, rechecks container
lifecycle, and records transient failures with a five-second recovery window.
Persistent failures still stop; the observed 12-GiB RSS threshold is unchanged.
CPU tests inject a process exit between enumeration and reading its RSS, and test
permission failure and persistent-monitor-loss handling. A real offline container
with short-lived child processes passed 35 samples and was removed. That live
check did not happen to hit a mid-read exit; the injected regression covers it.

Resume uses --resume-from with a fresh label and checks the unchanged routing
sources, original 40-task set, terminal outcomes, and prior cleanup. Completed
outcomes are carried forward without re-execution. Interrupted work is preserved
and retried in a new directory. method40-20261110b carries forward fastapi_12942
and fastapi_14246 from method40-20261110a and executes 38 remaining IDs.
