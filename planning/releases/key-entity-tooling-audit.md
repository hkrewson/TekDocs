# Development-tool audit observation — October 31, 2026

Disposition: open follow-up before the next development-tool refresh and final
1.0 release validation. This is an observed preexisting tooling finding, not a
new risk acceptance or a claim that the development environment audit passed.
Owner: TekDocs maintainer. Application runtime requirements are unchanged.

The existing development container's installed-environment `pip-audit` reported
14 advisories in three packages: filelock 3.32.2 (12 advisories, suggested fixed
version 4.2.1), msgpack 1.2.1 (CVE-2026-114613, fixed 1.2.3), and the build tool
setuptools 84.0.0 (GHSA-xmj3-9gf7-h52w, fixed 84.1.0). These packages are absent
from `backend/requirements.lock`; filelock/msgpack are in the development lock,
and setuptools is in the build lock. Their detailed reachability/severity has
not been independently assessed. Do not equate a clean application dependency
scan with a clean build/development toolchain.

The same container's scan of the complete pinned application requirements
reported no known vulnerabilities. Bandit reported no findings. Frontend audit
reported the six existing low findings; license policy passed. Exact-source
hosted application/image scans remain required. Updating and validating tooling
locks is separate work; no lockfiles or runtime dependencies change in this slice.
