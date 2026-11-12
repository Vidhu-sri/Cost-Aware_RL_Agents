Requests-only evaluation image context, prepared 2026-10-15.

imp.py and telnetlib.py are byte-for-byte copies from data/docker/.
Dockerfile.public copies the published data/docker/Dockerfile.public and
adds task-specific installation lines for pytest-httpbin==2.1.0 and
iproute2. The
installed swegemma injector explicitly skips that wheel, while the
Requests snapshot requires its fixture. The base image is python:3.13-slim,
pulled as
sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f.

The wheels/ directory was downloaded from PyPI using pip's binary-only
Python 3.13 resolver. Direct requirements came from the requests_7505
snapshot's pyproject.toml and requirements-dev.txt:

    pytest-httpbin==2.1.0
    httpbin~=0.10.0
    trustme
    pytest>=3,<10
    pytest-cov
    pytest-mock
    pytest-xdist
    PySocks>=1.5.6,!=1.5.7
    charset-normalizer>=2,<4
    idna>=2.5,<4
    urllib3>=1.26,<3
    certifi>=2023.5.7

The remaining wheels are resolver-selected transitive dependencies. See
wheels.sha256 for the exact resolved files and hashes. This is a local,
task-specific substitute for the absent published repository wheel set;
it is not evidence that these are the official Kaggle wheel versions.
The harness/model data/wheelhouse was not used.
