# Security Baseline

TekDocs targets the current OWASP ASVS Level 2 controls appropriate to a self-hosted business application.

## Non-negotiable controls

- Same-origin, HTTP-only, secure production session cookies with CSRF middleware enabled.
- Invite-only registration after a one-time owner bootstrap.
- MFA for privileged roles and secret reveal.
- Central policy authorization with cross-tenant and cross-client negative tests.
- Strict Markdown/HTML sanitization, Content Security Policy, and no executable raw HTML or MDX.
- Envelope encryption for managed secrets with the wrapping key supplied outside the database.
- Redacted structured logs, append-only audit records, scoped API/service credentials, and webhook replay protection.
- SSRF-resistant outbound integration and monitoring requests.
- Dependency, license, secret, source, container, and browser security gates.

Production startup must fail for missing or placeholder secrets, wildcard hosts/origins, insecure cookies, debug mode, or an unsupported database configuration.

See `docs/THREAT_MODEL.md` for the initial abuse analysis. Security reports are handled according to root `SECURITY.md` once the public repository is published.
