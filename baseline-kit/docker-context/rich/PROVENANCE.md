# Rich reference image context

Task: `rich_4070` (`Textualize/rich`). Snapshot SHA-256:
`d98b9e30af5d0b278016d5306a9ae33dc9636e808f90929cc6ab1204f8cd2b2d`.
Published reference patch SHA-256:
`34bb36c1ad55293e2e7996610ba6e6f6281dd5b20e3b36daeecaee7e7ce400dd`.
Official test patch SHA-256:
`f03185835b98a91393dbefebe80f68c4165b6cdc67b4abcee7985108fe079037`.

`Dockerfile.public`, `imp.py`, and `telnetlib.py` were copied from `data/docker/`.
The Dockerfile adds an offline install of selected runtime and test
packages after the published `COPY wheels/` step and `iproute2` for the
tested runner's private disconnected veth. The snapshot's
`pyproject.toml` declares Pygments `^2.13.0` and `markdown-it-py>=2.2.0`.
Its `poetry.lock` pins Pygments 2.19.2, markdown-it-py 3.0.0, mdurl 0.1.2,
pytest 7.4.4, pytest-cov 3.0.0, and typing-extensions 4.13.2. Optional
Jupyter packages and lint/type-check tools are not staged for the official
syntax and console tests.
The same lock pins coverage 7.6.1, iniconfig 2.1.0, packaging 25.0,
and pluggy 1.5.0; those test-tool dependencies are staged explicitly.

The earlier Bubblewrap reference run used host Pygments 2.21.0 and failed six
exact syntax-rendering assertions. Its broken-pipe assertion separately saw
producer exit 0 where the test expects 1; that may depend on pipe scheduling
or buffering and needs an execution-condition check in the Docker run.

All packages in `requirements-download.txt` were downloaded as Python 3.13
Linux wheels with `pip download`; exact files and hashes are recorded in
`wheels.sha256`. This local wheel set does not establish Kaggle equivalence.

Reference check `docker-rich-reference-20261015a-reference` used image
`sha256:b37838d31ec28ceeb079d5e044833890c974fee1eb72989279b74351f3706a9d`.
It returned 118 passed, 6 failed, all in `tests/test_syntax.py`; the
broken-pipe test passed. The live container had Pygments 2.21.0 and
pytest-cov 7.1.0 despite image pins of 2.19.2 and 3.0.0. The installed
`swegemma.harness.container_setup._build_unpacked_wheels_tar` reuses
`/tmp/swegemma_sp_cache_v8/sp_base.tar` by constant name without hashing the
selected wheel set. That tar contains `pygments-2.21.0.dist-info` and
`pytest_cov-7.1.0.dist-info`; the setup path extracted it over the image's
site-packages. The syntax failures therefore occurred under the wrong
Pygments version. This does not prove that correcting the injection will
make every syntax test pass; a fresh verification is needed.

Fresh reference check `docker-rich-reference-20261015b-reference` used the
same image ID after the Rich-only runner guard skipped the stale base archive.
The post-setup container reported Python 3.13.16, Pygments 2.19.2 imported
from `/usr/local/lib/python3.13/site-packages/pygments/__init__.py`, pytest
7.4.4, pytest-cov 3.0.0, markdown-it-py 3.0.0, mdurl 0.1.2, and
typing-extensions 4.13.2. Rich imported from `/workspace/rich/__init__.py`.
All 124 official target tests passed; the run did not time out and left no
owned containers. The original failed result remains preserved separately.
