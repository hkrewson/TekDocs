# TekDocs

TekDocs is a greenfield, self-hosted MSP knowledge and inventory platform centered on addressable, reusable documentation blocks. The project is pre-alpha at version `0.0.8`.

## Start locally

Requirements: Docker with Compose, Node.js 24, npm, and OpenSSL.

```sh
make bootstrap
make up
```

Open <http://localhost:3200>. `make bootstrap` creates an ignored `.env` with generated local secrets, installs the frontend lockfile, and builds the images. For an existing `.env`, it only adds newly required generated values and never replaces an existing value.

Development email is captured by Mailpit at <http://127.0.0.1:8025>; its UI is bound only to the local machine. Use `make mail-test EMAIL_TO=you@example.com` to verify delivery through the configured backend. Do not use real customer addresses or content in the development inbox. See `docs/EMAIL.md` for production SMTP configuration.

Invitation issuance is currently API-only and restricted to the installation owner. Configure the externally reachable `TEKDOCS_PUBLIC_URL` before sending invitations or password-reset links, and see `docs/INVITATIONS.md` and `docs/AUTHENTICATION.md` for token and lifecycle behavior.

Authenticated users can open **Profile → Settings** to review active browser sessions and revoke any session other than the one currently in use.

### First-owner bootstrap

Open TekDocs in a browser and enter `TEKDOCS_BOOTSTRAP_TOKEN` from the deployment secret store when prompted. The form keeps the token and password only long enough to submit the request, clears both fields immediately, and signs the new owner into a normal server-side session. Do not copy the token into tickets, chat, logs, or screenshots.

The narrow API remains available for automated setup:

```sh
curl --fail-with-body http://localhost:3200/api/v1/bootstrap/owner \
  --header 'Content-Type: application/json' \
  --header 'X-TekDocs-Bootstrap-Token: <deployment-secret>' \
  --data '{"tenant_name":"Example MSP","owner_email":"owner@example.com","owner_display_name":"Primary Owner","password":"use-a-unique-password-manager-generated-value"}'
```

`GET /api/v1/bootstrap/status` returns only whether bootstrap is required. A successful claim creates one tenant and one normal product owner identity, records a value-free audit event, and permanently closes this endpoint. Rotate the deployment bootstrap token after success and retain the replacement in the deployment secret store because production validation requires it; changing it does not reopen the database state. Public registration remains closed. See `docs/AUTHENTICATION.md` for the session and CSRF contract.

Useful gates:

```sh
make check
make test
make test-compose
make test-e2e
make security
```

The running Docker stack is authoritative for runtime claims. See `docs/PRODUCT_CHARTER.md`, `docs/ROADMAP.md`, and `AGENTS.md` before substantive work.

## Current boundaries

- Registration is deliberately closed. Owners issue invitations through controlled APIs; recipients can activate a verified account and recover its password through single-use links.
- The documentation route contains an executable Milkdown feasibility spike; it does not persist content yet.
- Tenant/entity/link models establish future data boundaries but are not yet exposed as CRUD APIs.
- Secret encryption and PDF rendering are feasibility primitives with tests, not user-facing vault/publication features.

## License

Copyright (C) 2026 TekDocs contributors. TekDocs is licensed under the GNU Affero General Public License version 3 only. See `LICENSE`, `TRADEMARKS.md`, and `CONTRIBUTING.md`.
