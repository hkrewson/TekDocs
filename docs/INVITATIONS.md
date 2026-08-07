# Invitation lifecycle

Only the installation owner can list, create, revoke, or resend invitations. TekDocs `0.0.6` lets a recipient accept a valid invitation to create a verified account and tenant membership. Public allauth signup remains closed.

## Lifecycle

`POST /api/v1/invitations` creates one tenant-scoped pending invitation and sends a multipart email. `POST /api/v1/invitations/{id}/resend` rotates the token, extends expiry, and sends a replacement. `POST /api/v1/invitations/{id}/revoke` clears the digest and permanently invalidates the invitation. `GET /api/v1/invitations` returns owner-visible lifecycle metadata but never token material.

`POST /api/v1/invitations/accept` accepts the token only in its JSON body and requires Django CSRF validation. The endpoint transactionally locks the pending invitation, validates the password through Django, creates the user, verified primary allauth email, and tenant membership, then records the accepting identity and clears the digest. It establishes a normal server-side session only after the transaction succeeds.

Only one pending invitation may exist for a tenant and normalized email address. Active duplicates and addresses already owned by a user return a conflict. An expired record is marked expired and retained for audit before a replacement is issued.

Email delivery is synchronous in this slice. If SMTP rejects a message, TekDocs retains the pending invitation, records a value-free failure event, and returns a generic error. The owner can then use the resend endpoint. The API response, audit metadata, and application logs must not contain the email token.

## Token handling

Tokens are generated with Python's maintained `secrets` module at 256 bits of randomness. PostgreSQL stores only the SHA-256 digest. Resending replaces that digest, while expiry and revocation clear it. Comparison uses constant-time matching and also requires a pending, unexpired record.

The email places the raw token after the `#` fragment marker in the acceptance URL. URL fragments are not sent in ordinary HTTP requests, reducing exposure through proxy and access logs. The browser reads the token into memory, immediately removes the fragment with history replacement, and never writes the token or password to browser storage. The token still grants account-activation authority and must not be copied into tickets, chat, screenshots, analytics, or logs.

Invalid, expired, revoked, already accepted, and concurrently reused tokens return the same unavailable response. Password-validation failure does not consume the invitation or retain partial user, email, or membership records. Concurrent acceptance is serialized by the invitation row lock; exactly one request can create the account.

## Deployment configuration

- `TEKDOCS_PUBLIC_URL` is the externally reachable base URL used to construct invitation links. Production requires HTTPS by default and rejects credentials, query strings, or fragments in the configured value.
- `TEKDOCS_ALLOW_INSECURE_PUBLIC_URL=true` is a local-development exception for `http://localhost:3200`; do not enable it for an untrusted network.
- `INVITATION_TTL_HOURS` defaults to 168 hours and must be between 1 and 2160.

SMTP configuration remains documented in `docs/EMAIL.md`.
