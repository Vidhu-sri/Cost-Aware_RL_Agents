# HTTPX reference image context

Task: `httpx_3672` (`encode/httpx`). Snapshot SHA-256:
`d1afdad9b9d433ebc345968ed90c4c401ed82f5fdfd27ab82eeaf92a49d9e2ed`.
Published reference patch SHA-256:
`e8e422a9bcfc7749dfacb456e7045646a1aa7feb678e1309f51637116fb562ce`.
Official test patch SHA-256:
`84351ec69acd45dd26342a533bf13faa3ebf2784bf74d8e177671b697620bb09`.

`Dockerfile.public`, `imp.py`, and `telnetlib.py` were copied from `data/docker/`.
The Dockerfile adds an offline install of task-specific test/runtime
packages after the published `COPY wheels/` step and `iproute2` for the
tested runner's private disconnected veth. The snapshot's
`pyproject.toml` declares `certifi`; its source also imports `idna`. The root
`requirements.txt` pins `pytest==8.3.5` and `pytest-cov==6.1.1` and lists
build, type-check, mirroring, and documentation tools not needed by the
official `tests/test_parsers.py` target.

Already staged from the separate Requests wheel context, byte-for-byte:

- `certifi-2026.7.22-py3-none-any.whl`: SHA-256 `62f22742b58a1a33014a2b6b706588a8d7e2a88ae7bd1a6ebe8c992928483775`
- `idna-3.20-py3-none-any.whl`: SHA-256 `ab7ae7122974553370f0bdb919e1a960b2cd1bc1ef0276416d896db81c14582c`

`pytest==8.3.5`, `pytest-cov==6.1.1`, and their resolver-selected dependencies
were downloaded as Python 3.13 Linux wheels with `pip download`; the exact
files and hashes are recorded in `wheels.sha256`. The resolver selected
coverage 7.16.2, iniconfig 2.3.1, packaging 26.3, and pluggy 1.7.0.
This local wheel set does not establish Kaggle package equivalence.
