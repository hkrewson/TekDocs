# TekDocs

TekDocs is a greenfield, self-hosted MSP knowledge and inventory platform centered on addressable, reusable documentation blocks. Version `0.8.1` adds authenticated encrypted recovery for PostgreSQL, managed media, and deployment keys under a separately custodied recovery key. TekDocs does not store or retrieve customer credential values.

## Start locally

Requirements: Docker with Compose, Node.js 24, npm, and OpenSSL.

```sh
make bootstrap
make up
```

Open <http://localhost:3200>. `make bootstrap` creates an ignored `.env` with generated local secrets, installs the frontend lockfile, and builds the images. For an existing `.env`, it only adds newly required generated values and never replaces an existing value.

Compose runs schema changes through a one-shot migration container using the database owner. Web, worker, and scheduler containers connect as the fixed, non-owner `tekdocs_runtime` role and validate its forced-RLS policy inventory before startup. Python installs use reviewed hash locks; run `./scripts/update-python-locks.sh` after intentionally changing backend requirements.

Development email is captured by Mailpit at <http://127.0.0.1:8025>; its UI is bound only to the local machine. Use `make mail-test EMAIL_TO=you@example.com` to verify delivery through the configured backend. Do not use real customer addresses or content in the development inbox. See `docs/EMAIL.md` for production SMTP configuration.

Production-capable secret files are configured with `.env.production.example`, `compose.production.yml`, and `compose.secret-files.yml`. Optional authenticated SMTP, OIDC, and first-owner bootstrap secrets use their own least-scope overlays. Direct and file sources are mutually exclusive; invalid files fail startup without echoing values or host paths. See `docs/SECRET_FILES_AND_PRODUCTION_IMAGES.md` and `docs/ONEPASSWORD_RUNTIME_INJECTION.md` before using this deployment boundary.

Supported encrypted backup and restore commands, custody requirements, and destructive safeguards are documented in `docs/BACKUP_AND_RECOVERY.md`. Run `make supported-recovery-rehearsal` to prove a complete isolated restore; possessing a backup without its separate recovery key is intentionally insufficient.

Invitation issuance is currently API-only and restricted to the installation owner. Configure the externally reachable `TEKDOCS_PUBLIC_URL` before sending invitations or password-reset links, and see `docs/INVITATIONS.md` and `docs/AUTHENTICATION.md` for token and lifecycle behavior.

Authenticated users can open **Profile → Settings** to update their display name, manage two-factor authentication, review active browser sessions, and revoke any session other than the one currently in use. Optional OpenID Connect configuration is documented in `docs/AUTHENTICATION.md`.

The installation owner can open **Organizations** to create, classify, edit, filter, and archive client, vendor, manufacturer, and partner records. An organization may hold more than one classification. Clicking its title opens a stable organization-workspace URL. The workspace control searches the authorized organization directory, preserves equivalent section routes when switching, exposes the union of classification capabilities, and always provides a return to the MSP workspace.

**Profile → Access control** manages built-in MSP roles, organization access modes, explicit client-by-client MSP staff assignments, access collections, and custom roles scoped to the tenant, one organization, or one collection. An assignment allows an existing role to reach an assigned-only client; it never grants permissions or replaces MFA. The entity/RBAC foundation is certified for the supported one-MSP-per-installation topology.

The **Custom fields** area defines validated extensions for Organization, Person, Site, and Location entities. MSP-wide definitions are inherited by matching client records, while organization definitions stay inside their owning workspace. Each definition change creates an immutable version; existing values retain the exact version that validated them. The first value-entry workflow is available from Site and Location rows.

The **Documentation** area persists workspace-owned Markdown in immutable, reusable block revisions. It offers visual block controls, raw Markdown, secure preview, revision history, live/pinned reuse, references, templates, managed attachments, and immutable signed STATIC publications with retained PDFs. Semantic highlight uses `==important context==`; NOTE, TIP, IMPORTANT, WARNING, and CAUTION callouts use the portable blockquote form `> [!WARNING]`. Raw HTML, MDX, scripts, inline styles, and document-authored CSS are intentionally unsupported.

Vendor and manufacturer workspaces expose **Products** for supplier-owned hardware/software families, concrete models, and reusable specification sets. Specification versions and model revisions are immutable and checksummed; stale edits fail without overwriting either writer. Client asset instantiation and retained supplier provenance follow in `0.3.4`.

### First-owner bootstrap

Open TekDocs in a browser and enter `TEKDOCS_BOOTSTRAP_TOKEN` from the deployment secret store when prompted. The form keeps the token and password only long enough to submit the request, clears both fields immediately, and signs the new owner into a normal server-side session. Do not copy the token into tickets, chat, logs, or screenshots.

The narrow API remains available for automated setup:

```sh
curl --fail-with-body http://localhost:3200/api/v1/bootstrap/owner \
  --header 'Content-Type: application/json' \
  --header 'X-TekDocs-Bootstrap-Token: <deployment-secret>' \
  --data '{"tenant_name":"Example MSP","owner_email":"owner@example.com","owner_display_name":"Primary Owner","password":"use-a-unique-password-manager-generated-value"}'
```

`GET /api/v1/bootstrap/status` returns only whether bootstrap is required. A successful claim creates one tenant and one normal product owner identity, records a value-free audit event, and permanently closes this endpoint. A production deployment may then remove `compose.bootstrap-secret.yml` and the bootstrap-token source file; readiness requires the token only while the installation is unclaimed. Public registration remains closed. See `docs/AUTHENTICATION.md` for the session and CSRF contract.

Useful gates:

```sh
make check
make test
make test-compose
make test-e2e
make test-e2e-all
make test-e2e-live
make test-stabilization
make test-certification
make test-documentation-certification
make test-secret-files
make test-markdown
make compose-doctor
make production-image-rehearsal
make clean-install-rehearsal
make upgrade-rehearsal
make documentation-upgrade-rehearsal
make documentation-backup-rehearsal
make supported-recovery-rehearsal
make security
```

The running Docker stack is authoritative for runtime claims. Authentication operations are documented in `docs/OPERATOR_AUTHENTICATION.md`; the current regression fixture and upgrade contract are in `docs/PERFORMANCE_BASELINE.md` and `docs/MIGRATION_TESTING.md`. See `docs/PRODUCT_CHARTER.md`, `docs/ROADMAP.md`, and `AGENTS.md` before substantive work.

## Current boundaries

- Registration is deliberately closed. Owners issue invitations through controlled APIs; recipients can activate a verified account and recover its password through single-use links.
- The documentation foundation is certified for the implemented single-installation scope: persistence, revision/reuse, transfer, and immutable STATIC-publication contracts are active. The broader 1.0 capacity, concurrency, supported encrypted backup tooling, malware quarantine, and public GitHub Wiki remain later milestones.
- Organizations, People, Sites, Locations, versioned custom fields, typed Entity relationships, supplier catalogs, and MSP/client operational inventory are active entity-backed foundations. Every Entity has a non-null immutable MSP/organization Workspace owner; `Tenant` remains the supported one-MSP installation boundary and future hosted seam.
- TekDocs does not store customer credential values. Provider-neutral external credential references arrived in `0.3.1`; production runtime secret-file injection is implemented in `0.3.2`, with mandatory removal of environment fallback remaining assigned to `0.8.7`.

## License

Copyright (C) 2026 TekDocs contributors. TekDocs is licensed under the GNU Affero General Public License version 3 only. See `LICENSE`, `TRADEMARKS.md`, and `CONTRIBUTING.md`.
