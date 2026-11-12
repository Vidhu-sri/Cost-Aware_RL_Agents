# FastAPI reference image context

The 67 published `fastapi/fastapi` tasks have Python 3.13-compatible
snapshots. Their `pyproject.toml` files declare a common runtime set:
Starlette, Pydantic, typing-extensions, and (in most snapshots)
annotated-doc. Starlette constraints differ across snapshots; 0.47.3
satisfies every declared range inspected. The context also stages the
test-client, optional runtime, and test packages in
`requirements-download.txt` for the official patched test targets.

`Dockerfile.public`, `imp.py`, and `telnetlib.py` were copied from
`data/docker/`. This derivative installs the local wheel set offline and
adds `iproute2` for the runner's private disconnected veth. The 68 wheels
were downloaded for CPython 3.13 Linux using `pip download`; exact files
and SHA-256 hashes are in `wheels.sha256` (15,099,254 total bytes).

The image is a local preflight environment. The selected package versions
are recorded by the wheel manifest and the image build, and may differ from
the published evaluator's hidden environment. A representative reference
check is required before using this context for the full preflight.

Representative check `fastapi_15661` with label
`fastapi-context-check-20261015a` passed 16 tests in the official target.
The container imported FastAPI from `/workspace/fastapi/__init__.py` and
reported Starlette 0.47.3, Pydantic 2.14.1, pytest 9.1.1, HTTPX 0.28.1,
and inline-snapshot 0.36.1. It did not time out or leave an owned container.
Image ID: `sha256:3db2aeda87c11d0df3b550926ccb23fe320d955da9121972b7a6ae62708bc373`.
