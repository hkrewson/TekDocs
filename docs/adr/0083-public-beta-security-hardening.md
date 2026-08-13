# ADR 0083: Public-beta production and security boundary

## Status

Accepted for `0.8.7`.

## Decision

- The supported production overlay sets `TEKDOCS_REQUIRE_SECRET_FILES=true`. Django rejects a direct or missing source for every required application/database key and for configured SMTP/OIDC credentials. Direct values remain a development-stack compatibility mechanism, not a supported production deployment.
- Migration, web, worker, and scheduler containers use the production image, read-only root filesystems, `/tmp` tmpfs, all Linux capabilities dropped, `no-new-privileges`, process ceilings, and bounded graceful shutdown. The frontend is read-only with only Nginx runtime paths writable in tmpfs.
- Application events use one bounded JSON formatter built on Python's maintained logging system. Only named correlation/operation fields survive; control characters and representative credentials are redacted, arbitrary record extras and exception text are discarded, and request logs use resolved route names instead of attacker-controlled URLs.
- Python and npm production dependency vulnerabilities and declared licenses are blocking local/hosted gates. Image, Action, lock, and DAST runtime inputs remain immutable pins.
- Scheduled/manual DAST runs a pinned ZAP passive baseline inside the same isolated production-target rehearsal. No ZAP DOM, request, response, authentication, or report artifact is retained.

## Limits

Local image builds are not signed published artifacts; SBOM, digest, attestation, and provenance closure remains `0.9.4`. Passive unauthenticated DAST complements rather than replaces the authenticated abuse, IDOR, SSRF, upload, Markdown, and browser suites. Host and container administrators remain trusted. External security assessment remains `0.8.9`.
