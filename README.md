# TekDocs

TekDocs is a self-hosted MSP documentation and inventory platform built around reusable, addressable Markdown blocks. It supports one MSP per installation while enforcing explicit ownership and authorization boundaries for MSP and client data.

TekDocs is an active homelab project published for people who want to run, inspect, or adapt it. Version numbers mark tested development checkpoints rather than commercial product releases. Do not deploy it without tested backups, controlled access, and an upgrade plan.

## Development provenance

TekDocs is human-directed and built with AI assistance, primarily using OpenAI Sol. The maintainer defines the product, architecture, security boundaries, acceptance criteria, and release decisions. AI-produced implementation is treated as engineering work that must pass the same review, test, migration, isolation, and production-image gates as any other contribution.

The historical security review used Claude Opus 5 (High) for three maintainer-directed automated passes culminating in commit `32c72c0`. The 1.0 candidate will receive a new commit-matched [automated security review](https://github.com/hkrewson/TekDocs/wiki/Security-model). TekDocs has not received an independent human security assessment, penetration test, compliance audit, certification, or independent assurance, and 1.0 does not claim otherwise.

## Capabilities

- MSP, client, vendor, manufacturer, and partner workspaces
- Markdown-first documentation with visual editing, raw Markdown, secure preview, and URL-restorable revision history; focused document tools and retained publication sections survive refresh and browser navigation while ownership/review controls protect unfinished work
- Versioned procedure, troubleshooting, reference, system-overview, and change-runbook topics with publication preflight
- Workspace-governed hierarchical taxonomies, exact legacy-tag migration, and searchable controlled terms
- Live and pinned reusable blocks with backlinks, impact previews, detach behavior, and entity references; client template and reusable-block libraries provide paged search, section previews, protected creation drafts, and explicit template-update conflict review
- Permission-aware field and content keys with exact-revision export and publication snapshots
- Focused managed-file controls with retained primary versions, retryable PDF viewing, page search and keyboard navigation
- Document-wide protection for new documents, settings, inline content and monitored-source drafts
- Server-backed document health queues and searchable, paged document-link insertion
- Immutable STATIC publications with signed manifests and retained PDF artifacts; protected publication/decision drafts and retryable audience checks ignore superseded responses; retained Content/Downloads/History sections and focused editable exports keep lifecycle actions and explicit ZIP file choices accessible
- People, sites, locations, custom fields, and typed entity relationships
- Permission-aware workspace search across documentation content and operational identifiers
- Hardware and software inventory, product catalogs, licenses, warranties, costs, contracts, and lifecycle history
- MSP-wide stock supplies with exact quantities, vendor provenance, client-use history, and invoice-line pricing
- Draft and immutable issued invoices with reviewable invoice-specific sender/bill-to details, complete linked revision drafts, billing units, payment instructions, retained PDFs, CSV/accounting exports, delivery history, and exact-client portal access
- Lightweight network documentation with five focused views for CIDRs, asset-backed devices, DNS, Wireless and NetBox evidence; CIDRs retain optional VLAN, DHCP and DNS facts plus useful IP-to-asset assignments without recreating an IPAM or network controller
- Client publication controls, portal access, notifications, reminders, domains, and certificate monitoring
- Scoped built-in and custom roles at MSP, organization, and collection boundaries
- Public API, personal and service tokens, signed webhooks, integration jobs, reconciliation, and sanitized Git export
- Exact-Workspace NetBox and read-only UniFi Network, Microsoft 365/Entra/Intune, HaloPSA, and NinjaOne integrations with encrypted credentials; NetBox projects supported prefixes and devices into CIDRs and hardware Assets automatically, while separately credentialed UniFi-to-NetBox changes require an exact reviewed proposal and audit event
- Dry-run, idempotent Workspace imports for native bundles and documented ITFlow, IT Glue, Hudu, and TekDocs CSV mappings
- Compliance controls, evidence, risks, reviews, and immutable evidence bundles

TekDocs stores provider-neutral credential references. It does not store or retrieve customer credential values.

Invoices are a bounded issuance capability with immutable artifacts, append-only lifecycle projections, and a versioned accounting handoff; TekDocs is not a general ledger or payment processor. Ticketing, PSA, CRM, RMM, and MDM workflows remain in their authoritative external systems and may be projected through explicit integrations. The maintained [product capability contract](docs/PRODUCT_BOUNDARY.md) distinguishes current, intended 1.0, experimental, and excluded behavior.

The accepted [version 1 delivery plan](planning/v1-markdown-content-graph.md)
makes Markdown documents and reusable fragments canonical in TekDocs-managed
local Git repositories while PostgreSQL retains permissions, workflow,
publications, audit and operational data. The frozen `0.9.0` runtime remains the
database-first migration baseline; repository implementation begins in `0.9.1`
and requires no GitHub organization or hosted Git service.

### Version 1 repository content profile

The `0.9.2` checkpoint defines the first canonical repository content contract.
Every authored `*.md` file starts with strict, versioned YAML frontmatter and is
either a `document` or a reusable `fragment`:

```markdown
---
schema: tekdocs.content/v1
id: 8eb6ae2c-0e92-41e9-b0d6-f4e2eab1bfcc
kind: document
title: Laptop enrollment
properties:
  lifecycle: active
taxonomies:
  service-area:
    - endpoint-management
---

See [[fa31a88f-c766-47d1-82bf-6a91859f2ef0|Enrollment prerequisites]].
```

IDs and metadata remain portable in Git. PostgreSQL holds a disposable,
authorization-scoped projection of the accepted commit: nodes, portable
properties, outgoing links, backlinks, unresolved-link findings, topic checks,
and the indexed commit. Rebuilding the projection produces the same digest and
API result. A structurally invalid accepted commit is recorded as rejected and
does not replace the last-known-good projection.
During the `0.9.6` migration window, a document may also carry a bounded
`key_bindings` mapping from field-key names to stable Entity IDs. Git stores
neither resolved values nor secret data; matching legacy bindings and the
reader's field permissions still control live resolution until repository
binding authority is implemented.

The read-only migration-status endpoint reports copy parity and explicit
`handoff_blockers`. For an `in_sync` copy, `read_projection_state` also checks
the permission-scoped repository detail route against the legacy title,
composed Markdown and reader-visible rendered HTML, plus viewer-visible
outgoing legacy `references` links. Before reporting `in_sync`, status also
rechecks the bytes of every active ordinary attachment retained outside Git;
a missing or altered file marks the copy `diverged` and leaves the read
projection unchecked.
This is a narrow shadow check, not full read parity or an
authority transition: legacy reads and writes remain authoritative until their
parity and publication gates are implemented and verified.
Copy parity also checks indexed portable properties, taxonomies, topic identity,
title and Markdown against the parsed repository source, then re-reads each
copied file from the accepted Git revision to require its exact source bytes;
a stale derived row or missing/altered Git file is reported as `diverged`.
The corresponding index or Git source must be repaired before parity can
return. Ordered include edges must
also retain their targets, audience, resolution mode and live source digest.
Indexed wikilinks must retain their order, labels, fragments and resolved
backlink pointers; missing targets remain unresolved rather than fabricated.
Composed operational-entity links must agree with their indexed relationship
rows, and the document root must agree with the export's independently resolved
link list. A stale entity-context projection is `diverged`, not cutover-ready.
During the copy window, same-workspace legacy `references` links to supported
operational entities become neutral, permission-filtered repository mentions;
foreign or ambiguous relationships remain migration blockers.

For an operator-directed rebuild, run
`python manage.py index_workspace_content --repository <repository-uuid>` in
the backend container. Add `--force` to verify and replace an already-current
projection. Managed authoring indexes each accepted write and retries an
unfinished projection in the background. Existing database documents are not
automatically migrated. The bounded `0.9.6` operator procedure is in
[Legacy document copy](docs/DOCUMENT_MIGRATION.md); a copy never changes
legacy read or write authority.

### Version 1 fragment composition

The `0.9.3` checkpoint adds ordered `includes` to document and fragment
frontmatter. Each include names a fragment UUID, a `shared`, `msp_internal`, or
`client_visible` audience, and a `live` or `pinned` resolution mode. Pinned
includes also name the exact retained Git commit. Fragment files live under
the reserved `fragments/` directory. For example:

```yaml
includes:
  - id: fa31a88f-c766-47d1-82bf-6a91859f2ef0
    mode: live
    audience: shared
  - id: 18849678-16a8-460a-a887-69d0b3c275ae
    mode: pinned
    audience: msp_internal
    commit: 0123456789abcdef0123456789abcdef01234567
```

An independent copy is a new fragment with its own UUID and optional
`derived_from: {id, commit}` provenance. A document may also list exact
`template_sources: [{id, commit}]`; the index reports whether each source is
current, changed, or missing without changing template enrollment decisions.
The index stores exact source manifests and audience-specific expansions, and
rejects cycles, missing or foreign pins, audience widening, excessive depth,
node count, or expanded size. The current database-backed editor remains in
place through the later migration checkpoint.

### Version 1 operational context and read paths

The `0.9.4` checkpoint adds portable `entity_links: [{id, relationship}]`
metadata and narrative `[label](tekdocs://entity/<uuid>)` references. Valid
relationships are `setup`, `enrollment`, `maintenance`, `troubleshooting`,
`repair_event`, and `mention`. The accepted Git commit yields a rebuildable
entity-link projection, including links in composed fragments. Authorized
staff reads resolve current entity names instead of storing mutable labels or
serials in the relationship. Asset Documentation distinguishes exact-device,
model, and product-class guidance. Collection/search/health and document-detail
routes read the current workspace's index; raw repository content remains
unavailable to client portal users. The legacy editor and publication flow
remain unchanged until later checkpoints.

The in-progress `0.9.7` repository publication path retains complete primary-file
history in signed STATIC v2 records. A client-visible record still requires
independent release and delivery approval; portal access fails closed if any
retained version is missing or altered. This does not complete the document
authority handoff.

For supported promoted ordinary documents, Documentation now connects
**Publish document** to a current-Git readiness check and permanent internal
snapshots. **Publication history** opens retained legacy and Git versions for
correction, withdrawal, decisions and PDF downloads. See the
[bounded interface acceptance](planning/migrations/git-publication-interface.md)
for limitations and validation. The 0.9.16 candidate adds a real browser-to-database
acceptance journey for this workflow; production deployment remains separate.

The subsequent [file-backed migration slice](planning/migrations/file-backed-publication-migration.md)
extends this supported shape to clean managed files and every primary-file
version. File-bearing Git snapshots retain independent copies of those files
alongside their signed manifest and PDF. Migration leaves existing signatures,
PDFs, file identities and private storage unchanged; rollback retains files
uploaded under Git authority. Templates, unresolved references and client
delivery remain outside this boundary.

The [shared-block extension](planning/migrations/shared-block-publication-migration.md)
adds same-Workspace live and pinned leaf references to this internal workflow.
An explicit previewed group moves every live owner and consumer together. Pins
retain their selected Git revision; signed history and PDFs remain unchanged.
Rollback restores supported text edits to each original owner. Repeated block
occurrences, templates, cross-Workspace reuse and client delivery remain blocked.

### Managed repository authoring

The `0.9.5` checkpoint adds a separate **Repository content** editor under
Documentation for staff with document-edit permission. It creates Markdown
documents and reusable fragments, updates body and portable metadata, and
moves files while retaining old paths as same-repository aliases. Stable UUID
wikilinks and includes do not need rewriting when a file moves. The original
database-backed document editor remains available during the migration window;
editing it does not change the repository copy.

Each save names the exact accepted Git commit and source blob the editor read.
Unrelated repository changes may be merged safely, but concurrent changes to
the same file return base/current/proposed source for explicit review and
rebase. The service validates the entire candidate content graph before an
accepted commit, preserving comments and untouched frontmatter where possible.
If indexing is interrupted after acceptance, the accepted/indexed markers
show the lag and a scheduled retry rebuilds the projection without rewriting
Git. This is local managed Git; remote GitHub integration is not required.

Promoted legacy documents retain a reversible editing boundary: owned fragment
text can change, while root content/metadata, fragment metadata, file paths and
include structure are protected at Git acceptance. Native Git documents retain
normal authoring. The internal operator handoff procedure governs authority
changes; unsupported edits must return to legacy authority first. This guard
prevents new structural drift and does not repair previously diverged content.

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
- Node.js 24.22.1 (security-patched LTS toolchain)
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

Remaining pre-1.0 work is tracked in the [version 1 delivery plan](planning/v1-markdown-content-graph.md). The `0.9.0` baseline closes the database-first line and transfers final candidate interface, security, pilot, and recovery acceptance to the migrated system.

## Development gates

For a compact current-candidate status, run `make release-status`. Release evidence,
failed-run triage and disposable operator acceptance preparation are described in
[release operations](planning/releases/README.md). These tools keep the tested
application commit separate from subsequent evidence-only commits.

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

Prove the complete local repository foundation, including an interrupted write,
container recreation, encrypted backup, and network-isolated restore:

```bash
make repository-foundation-acceptance
```

Run security checks:

```bash
make security
```

Run the complete release gate:

```bash
make release-gate
```

The aggregate uses current-destination rehearsals; fixed-version historical
checkpoint targets remain standalone. See [release-gate composition](planning/releases/README.md#local-release-gate-composition).

Docker Compose results are authoritative for runtime claims.

`make test-worker-boundaries` checks integration and monitoring task scope
binding/cleanup alongside runtime isolation and production secret/settings
validation. Provider calls are replaced in the task-boundary tests; this does
not exercise broker delivery or live provider requests.

`make test-operations-security` checks outbox, webhook, notification, remote
document, worker and runtime isolation boundaries together, with external
transports replaced. `make test-database-error-security` checks safe database
conflict responses and related catalog, inventory, commercial, invoice and publication
regressions. Neither targeted gate replaces the final release/security review.
`make test-network-error-security` checks network error translation alongside
the network behavior suites and runtime isolation checks, without rerunning the
full permission matrix.
`make test-document-error-security` checks document/publication error boundaries
and existing authoring/composition behavior without the separate upgrade cases;
upgrade validation remains required for the final candidate.
`make test-integration-security` checks integration behavior, authorization and
runtime isolation, including safe NetBox link-failure messages. Its direct
error-boundary cases replace provider references and do not contact NetBox.
`make test-provider-security` adds the Microsoft Graph, HaloPSA, NinjaOne and
UniFi adapter/integration suites with provider traffic replaced. It complements
the shared integration-security gate without running frontend or upgrade suites.

`make test-imports` runs import parsing, preview/apply/rollback checks and the
shared permission/isolation regressions. Damaged ZIP members, duplicate bundle
filenames and CSV parser-limit failures are rejected before import staging.
CSV rows with extra values beyond their header columns are rejected rather than
silently truncated; quoted commas and blank optional cells remain supported.
Rows with malformed record types or external keys remain rejected in the
preview, using safe fallback labels without retaining their content. Any
rejected row blocks applying the batch.

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

`make test-recovery-archive` runs the focused Docker archive-authentication and
failed-decryption cleanup checks without a database. It does not replace the
complete supported recovery rehearsal above.

`make test-repository-recovery` also checks Git bundle validation, retained
commit recovery and retry after handled restore failures. It uses an isolated
test database and disposable repository directories, not production volumes.

Current recovery sets include PostgreSQL, managed media, every managed local Git
repository, and the allowlisted deployment secrets. Backup briefly pauses active
TekDocs writers to keep accepted Git heads aligned with the database snapshot.
It checks every retained managed document file against its database size and
SHA-256 before publishing a recovery set; missing or changed files abort the
backup. Restore validates all encrypted components and repository bundles before
destructive work, then verifies the restored repositories, publications, and
managed files against PostgreSQL before reporting success.
Offline archive preflight runs as the invoking host user so it can read the
private decrypted working directory on native Linux. Runtime repository restore
and verification retain the application user and receive only a read-only
repository-archive file mount, not the directory containing decrypted keys.
Deployment-secret archives must contain unique allowlisted regular files, each
1–4096 bytes, and all required keys. Links and special entries are rejected
before extraction or volume replacement.
Media archives accept only regular files and directories with unique relative
paths. Links, special/sparse entries, parent traversal, file/directory conflicts
and truncated file data are rejected before any volumes are replaced. Empty
media directories and empty regular files remain supported.
Restore pins every Compose operation to the project confirmed by
`--confirm-destroy`; an inherited `COMPOSE_PROJECT_NAME` cannot redirect it.
Use `--network-isolated` during a recovery rehearsal or controlled restore to
keep the restored stack off external networks until verification is complete.
GitHub and other optional remotes are replication targets, not backups, and are
never required for restore.
Secret capture excludes macOS archive sidecar metadata. Restored secret files
match production setup: root-owned and read-only inside a private `0700` host
directory, so unrelated native-Linux container users can read their scoped
Compose mounts without making the host directory public.

## API

The generated API reference is available on a running installation at:

```text
/api/v1/docs/
```

TekDocs uses session and CSRF authentication for the browser application. Personal tokens, service tokens, and webhook credentials use explicit scopes and separate security boundaries.

Bearer API tokens are accepted only under `/api/v1/`. Browser account,
authenticator and sign-in routes under `/_allauth/`, and administration routes
under `/admin/`, reject bearer headers,
including requests that also carry a valid browser session.
Profile edits at `/api/v1/auth/profile` also require a browser session and CSRF
token; personal and service API tokens cannot change account profiles.
Token management also rejects bearer headers, including malformed ones, rather
than falling back to an accompanying browser session.

OIDC server-to-server discovery, token, user-info, and signing-key requests use
the approved egress boundary: public DNS destinations over HTTPS port 443,
address pinning with hostname verification, no redirects, fixed connection/read
timeouts, and responses limited to 1 MiB. Private-address identity providers,
outbound proxies, and compressed responses are not supported by this profile.
Use direct public HTTPS endpoints for the configured provider.

Changing an integration's saved API destination requires a recently
authenticated browser session, in addition to integration-management permission
and MFA. The editor retains the draft while asking for password confirmation.
Name, schedule and pause/resume edits do not add this reauthentication step when
the destination is unchanged.

## GitHub automation

The repository uses three primary workflows:

- **Build, test, and secure** validates backend, frontend, and diagram-renderer code, PostgreSQL behavior, permissions, isolation, dependencies, licenses, repository secrets, browser journeys, and production containers. Successful trusted pushes publish the exact tested backend, frontend, isolated diagram-renderer, and patched Mailpit images to GHCR with commit-addressed tags, SBOM attestations, and build-provenance attestations.
- **Diagram renderer maintenance** is governed by a checked preview/export version contract and a [repeatable update procedure](.github/DIAGRAM_RENDERER_MAINTENANCE.md). CI retains the effective versions and hashes of the files that control diagram output.
- **Extended validation** runs the full browser matrix, reference performance dataset, backup and upgrade rehearsals, and DAST.
- **CodeQL** publishes Python and JavaScript/TypeScript findings through GitHub code scanning.

Dependabot submits grouped weekly updates for Python, npm, Docker, and GitHub Actions dependencies.

Production updates support explicit release selection with `scripts/update-production.sh --release vMAJOR.MINOR.PATCH` once this updater is installed. New version releases on `main` validate, publish and verify all four images, then atomically deliver the application and receipt tags in one CI run. The updater retrieves the CI receipt automatically; no receipt-only follow-up commit is needed. See the [single-push delivery contract](planning/releases/ci-release-delivery.md). Release mode checks the tag against a reviewed commit/image receipt, uses the tagged Compose configuration, and verifies the running application services against the approved digests. The tooling checkout stays unchanged; `.env` records `TEKDOCS_DEPLOYED_COMMIT` and image digests only after readiness and identity checks pass. Existing backup settings remain required. Without `--release`, the legacy upstream-branch update behavior remains. See the Wiki upgrade procedure for deployment instructions.

## Documentation

The [TekDocs Wiki](https://github.com/hkrewson/TekDocs/wiki) is the public product and operator manual. This repository does not maintain a second public documentation tree.

Markdown documents support Mermaid diagrams for network maps, flows, and other relationships kept directly beside the documentation they explain.

Before contributing, read `CONTRIBUTING.md`, the [interface-language contract](docs/UI_LANGUAGE.md), the public GitHub Wiki, and the current milestone or issue. Do not push, publish, tag, or deploy without explicit authorization. Keep machine-specific agent instructions local; they are excluded from version control.

## License

Copyright (C) 2026 TekDocs contributors.

TekDocs is licensed under the GNU Affero General Public License version 3 only. See `LICENSE`, `TRADEMARKS.md`, and `CONTRIBUTING.md`.
