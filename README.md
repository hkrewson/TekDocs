# TekDocs

TekDocs is a self-hosted MSP documentation and inventory platform built around reusable, addressable Markdown blocks. It supports one MSP per installation while enforcing explicit ownership and authorization boundaries for MSP and client data.

TekDocs is an active homelab project published for people who want to run, inspect, or adapt it. Version numbers mark tested development checkpoints rather than commercial product releases. Do not deploy it without tested backups, controlled access, and an upgrade plan.

## Development provenance

TekDocs is human-directed and built with AI assistance, primarily using OpenAI Sol. The maintainer defines the product, architecture, security boundaries, acceptance criteria, and release decisions. AI-produced implementation is treated as engineering work that must pass the same review, test, migration, isolation, and production-image gates as any other contribution.

The security review currently recorded by the project used Claude Opus 5 (High) for three maintainer-directed automated review passes culminating in commit `32c72c0`. The reviewer and method are identified explicitly in the review record. This work is not represented as an independent human assessment; a future human third-party review would provide useful additional assurance.

## Capabilities

- MSP, client, vendor, manufacturer, and partner workspaces
- Markdown-first documentation with visual editing, raw Markdown, secure preview, and revision history
- Versioned procedure, troubleshooting, reference, system-overview, and change-runbook topics with publication preflight
- Live and pinned reusable blocks with backlinks, impact previews, detach behavior, and entity references
- Permission-aware field and content keys with exact-revision export and publication snapshots
- Immutable STATIC publications with signed manifests and retained PDF artifacts
- People, sites, locations, custom fields, and typed entity relationships
- Permission-aware workspace search across documentation content and operational identifiers
- Hardware and software inventory, product catalogs, licenses, warranties, costs, contracts, and lifecycle history
- Simplified network records for locations, VLANs, CIDRs, ranges, gateways, DNS, and asset MAC addresses
- Client publication controls, portal access, notifications, reminders, domains, and certificate monitoring
- Scoped built-in and custom roles at MSP, organization, and collection boundaries
- Public API, personal and service tokens, signed webhooks, integration jobs, reconciliation, and sanitized Git export
- Dry-run, idempotent Workspace imports for native bundles and documented ITFlow, IT Glue, Hudu, and TekDocs CSV mappings
- Compliance controls, evidence, risks, reviews, and immutable evidence bundles

TekDocs stores provider-neutral credential references. It does not store or retrieve customer credential values.

Invoices are a bounded issuance capability; TekDocs is not a general ledger or payment processor. Ticketing, PSA, CRM, RMM, and MDM workflows remain in their authoritative external systems and may be projected through explicit integrations. The maintained [product capability contract](docs/PRODUCT_BOUNDARY.md) distinguishes current, intended 1.0, experimental, and excluded behavior.

## Production setup

Use the [TekDocs Setup](https://github.com/hkrewson/TekDocs/wiki/TekDocs-Setup) guide for production Compose, secret files, Traefik, first-owner creation, MFA enrollment, verification, and bootstrap removal.

The production setup command creates the environment and file-backed secrets, pins the tested GHCR images for the current commit, validates Traefik and Compose, starts TekDocs, and prints the one-time deployment token:

```bash
scripts/setup-production.sh \
  --domain docs.example.com \
  --secret-directory /absolute/path/to/tekdocs-secrets \
  --timezone America/Chicago
```

The first owner must complete these steps in order:

1. Create the MSP workspace with the deployment token.
2. Enroll a TOTP authenticator using the displayed QR code.
3. Save and acknowledge the recovery codes.
4. Confirm the owner can sign in.
5. Run `scripts/setup-production.sh --finalize`; it verifies bootstrap completion, removes the bootstrap boundary, and deletes the bootstrap-token file.

Owners and administrators must enroll TOTP before TekDocs permits privileged actions.

## Local development

Requirements:

- Docker Engine with Docker Compose
- Node.js 24
- npm 11
- OpenSSL

Create the local environment and start TekDocs:

```bash
make bootstrap
make up
```

Open:

```text
http://localhost:3200
```

Mailpit captures development email at:

```text
http://127.0.0.1:8025
```

`make bootstrap` creates an ignored `.env`, generates local-only secrets, installs frontend dependencies, and builds the images. Existing environment values are not replaced.

Operator, maintenance, and validation commands live in `scripts/`. Regression fixtures and Docker/browser/upgrade rehearsals live in `tests/rehearsals/` and remain available through their existing `make` targets.

## Runtime

- Django 5.2 LTS and Django REST Framework
- PostgreSQL 17
- Celery and Valkey
- React 19, TypeScript, and Vite
- Nginx frontend proxy
- Docker Compose

Database migrations run through a one-shot owner container. The web, worker, and scheduler services use the restricted `tekdocs_runtime` PostgreSQL role and validate the row-level security policy inventory before startup.

Production secrets are file-backed. Direct environment values and secret-file sources are mutually exclusive in the production profile.

## Development gates

Run the fast local gate:

```bash
make check
```

Run the complete unit and component suites:

```bash
make test
```

Run production-shaped and browser validation:

```bash
make test-compose
make test-e2e
make production-image-rehearsal
```

Run security checks:

```bash
make security
```

Run the complete release gate:

```bash
make release-gate
```

Docker Compose results are authoritative for runtime claims.

## Backup and recovery

Create and restore supported encrypted backups with:

```text
scripts/tekdocs-backup.sh
scripts/tekdocs-restore.sh
```

Verify the recovery path before deployment:

```bash
make supported-recovery-rehearsal
```

Store the recovery key separately from the backup. Neither is sufficient without the other.

## API

The generated API reference is available on a running installation at:

```text
/api/v1/docs/
```

TekDocs uses session and CSRF authentication for the browser application. Personal tokens, service tokens, and webhook credentials use explicit scopes and separate security boundaries.

## GitHub automation

The repository uses three primary workflows:

- **Build, test, and secure** validates backend, frontend, and diagram-renderer code, PostgreSQL behavior, permissions, isolation, dependencies, licenses, repository secrets, browser journeys, and production containers. Successful trusted pushes publish the exact tested backend, frontend, and isolated diagram-renderer images to GHCR with commit-addressed tags, SBOM attestations, and build-provenance attestations.
- **Extended validation** runs the full browser matrix, reference performance dataset, backup and upgrade rehearsals, and DAST.
- **CodeQL** publishes Python and JavaScript/TypeScript findings through GitHub code scanning.

Dependabot submits grouped weekly updates for Python, npm, Docker, and GitHub Actions dependencies.

Production updates pull the three images for the checked-out Git commit, verify their embedded revision labels, resolve them to immutable registry digests, and persist the deployed digests only after the public readiness check passes.

## Documentation

The [TekDocs Wiki](https://github.com/hkrewson/TekDocs/wiki) is the public product and operator manual. This repository does not maintain a second public documentation tree.

Documentation can also be assembled into versioned maps for operating manuals, recovery plans, onboarding, compliance, and client handoff. Map baselines retain a deterministic portable manifest, source content, checksums, and optional PDF or DOCX output.

Before contributing, read `AGENTS.md`, the applicable backend or frontend instructions, and the current milestone or issue. Do not push, publish, tag, or deploy without explicit authorization.

## License

Copyright (C) 2026 TekDocs contributors.

TekDocs is licensed under the GNU Affero General Public License version 3 only. See `LICENSE`, `TRADEMARKS.md`, and `CONTRIBUTING.md`.
