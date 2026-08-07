# TekDocs

TekDocs is a greenfield, self-hosted MSP knowledge and inventory platform centered on addressable, reusable documentation blocks. The project is pre-alpha at version `0.0.2`.

## Start locally

Requirements: Docker with Compose, Node.js 24, npm, and OpenSSL.

```sh
make bootstrap
make up
```

Open <http://localhost:3200>. `make bootstrap` creates an ignored `.env` with generated local secrets, installs the frontend lockfile, and builds the images. For an existing `.env`, it only adds newly required generated values and never replaces an existing value.

### First-owner bootstrap

Release `0.0.2` exposes a deliberately narrow API bootstrap; the browser flow follows in `0.0.3`. Retrieve `TEKDOCS_BOOTSTRAP_TOKEN` from the deployment secret store without copying it into tickets, chat, logs, or shell history, then send it as the `X-TekDocs-Bootstrap-Token` header:

```sh
curl --fail-with-body http://localhost:3200/api/v1/bootstrap/owner \
  --header 'Content-Type: application/json' \
  --header 'X-TekDocs-Bootstrap-Token: <deployment-secret>' \
  --data '{"tenant_name":"Example MSP","owner_email":"owner@example.com","owner_display_name":"Primary Owner","password":"use-a-unique-password-manager-generated-value"}'
```

`GET /api/v1/bootstrap/status` returns only whether bootstrap is required. A successful claim creates one tenant and one normal product owner identity, records a value-free audit event, and permanently closes this endpoint. Rotate the deployment bootstrap token after success and retain the replacement in the deployment secret store because production validation requires it; changing it does not reopen the database state. Public registration remains closed.

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

- Registration is deliberately closed. `0.0.2` provides only the deployment-authorized first-owner API; controlled invitations arrive in `0.0.4`.
- The documentation route contains an executable Milkdown feasibility spike; it does not persist content yet.
- Tenant/entity/link models establish future data boundaries but are not exposed as CRUD APIs in `0.0.2`.
- Secret encryption and PDF rendering are feasibility primitives with tests, not user-facing vault/publication features.

## License

Copyright (C) 2026 TekDocs contributors. TekDocs is licensed under the GNU Affero General Public License version 3 only. See `LICENSE`, `TRADEMARKS.md`, and `CONTRIBUTING.md`.
