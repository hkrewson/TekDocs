# Invitation issuance

TekDocs `0.0.5` provides the authenticated API foundation for issuing invitations. Only the installation owner can list, create, revoke, or resend invitations. Account activation and invitation-token consumption are deliberately deferred to `0.0.6`; receiving an email does not yet create a user or open registration.

## Lifecycle

`POST /api/v1/invitations` creates one tenant-scoped pending invitation and sends a multipart email. `POST /api/v1/invitations/{id}/resend` rotates the token, extends expiry, and sends a replacement. `POST /api/v1/invitations/{id}/revoke` clears the digest and permanently invalidates the invitation. `GET /api/v1/invitations` returns owner-visible lifecycle metadata but never token material.

Only one pending invitation may exist for a tenant and normalized email address. Active duplicates and addresses already owned by a user return a conflict. An expired record is marked expired and retained for audit before a replacement is issued.

Email delivery is synchronous in this slice. If SMTP rejects a message, TekDocs retains the pending invitation, records a value-free failure event, and returns a generic error. The owner can then use the resend endpoint. The API response, audit metadata, and application logs must not contain the email token.

## Token handling

Tokens are generated with Python's maintained `secrets` module at 256 bits of randomness. PostgreSQL stores only the SHA-256 digest. Resending replaces that digest, while expiry and revocation clear it. Comparison uses constant-time matching and also requires a pending, unexpired record.

The email places the raw token after the `#` fragment marker in the acceptance URL. URL fragments are available to the future browser activation page but are not sent in ordinary HTTP requests, reducing exposure through proxy and access logs. The token still grants future account-activation authority and must not be copied into tickets, chat, screenshots, analytics, or logs.

## Deployment configuration

- `TEKDOCS_PUBLIC_URL` is the externally reachable base URL used to construct invitation links. Production requires HTTPS by default and rejects credentials, query strings, or fragments in the configured value.
- `TEKDOCS_ALLOW_INSECURE_PUBLIC_URL=true` is a local-development exception for `http://localhost:3200`; do not enable it for an untrusted network.
- `INVITATION_TTL_HOURS` defaults to 168 hours and must be between 1 and 2160.

SMTP configuration remains documented in `docs/EMAIL.md`.
