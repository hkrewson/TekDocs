# TekDocs

TekDocs is a greenfield, self-hosted MSP knowledge and inventory platform centered on addressable, reusable documentation blocks. The project is pre-alpha at version `0.0.1`.

## Start locally

Requirements: Docker with Compose, Node.js 24, npm, and OpenSSL.

```sh
make bootstrap
make up
```

Open <http://localhost:3200>. `make bootstrap` creates an ignored `.env` with generated local secrets, installs the frontend lockfile, and builds the images. It never overwrites an existing `.env`.

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

- Registration is deliberately closed until the audited bootstrap/invitation flow in `0.1.0`.
- The documentation route contains an executable Milkdown feasibility spike; it does not persist content yet.
- Tenant/entity/link models establish future data boundaries but are not exposed as CRUD APIs in `0.0.1`.
- Secret encryption and PDF rendering are feasibility primitives with tests, not user-facing vault/publication features.

## License

Copyright (C) 2026 TekDocs contributors. TekDocs is licensed under the GNU Affero General Public License version 3 only. See `LICENSE`, `TRADEMARKS.md`, and `CONTRIBUTING.md`.
