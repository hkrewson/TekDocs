# Release Roadmap

The authoritative product scope is `docs/PRODUCT_CHARTER.md`. Patch releases are small, independently testable roadmap slices. Minor releases are stabilization checkpoints: they add no major capability and certify that the preceding patch line works as a coherent subsystem.

Most patch slices should fit one to three focused engineering sessions. A slice that grows beyond its stated exit condition must be split rather than silently expanded. Dates follow demonstrated velocity; security, migration, isolation, backup, and upgrade gates never compress to preserve a date.

## Release-line overview

| Stable release | Capability certified |
| --- | --- |
| `0.0.1` | Greenfield repository and delivery foundation. |
| `0.1.0` | Secure identity, authentication, owner administration, and tenant shell. |
| `0.2.0` | Addressable entities, MSP/client organization model, scoped RBAC, and isolation. |
| `0.3.0` | Reusable Markdown documentation and immutable STATIC publication. |
| `0.4.0` | Encrypted credentials and hardware/software inventory. |
| `0.5.0` | Network inventory and relationship-derived views. |
| `0.6.0` | Controlled client portal, publication workflow, and notifications. |
| `0.7.0` | Stable integration API, provider runtime, webhooks, and reconciliation. |
| `0.8.0` | Compliance evidence plus safe domain and certificate monitoring. |
| `0.9.0` | Feature-complete public beta and operational hardening. |
| `1.0.0` | Supported public release with final security and supply-chain evidence. |

## Foundation and authentication: `0.0.x` → `0.1.0`

| Release | Status | Slice and exit condition |
| --- | --- | --- |
| `0.0.1` | Complete | Governance, threat model, repository, Compose stack, Django/React skeleton, OpenAPI, CI, design system, and feasibility spikes. |
| `0.0.2` | Complete | One-time installation state and first-owner API protected by a deployment bootstrap secret. Concurrent/repeated claims and public signup fail safely. |
| `0.0.3` | Complete | Accessible browser bootstrap, sign-in/sign-out, CSRF lifecycle, and authenticated shell boundary. |
| `0.0.4` | Complete | SMTP configuration boundary, transactional email templates, operator delivery check, and development Mailpit capture. |
| `0.0.5` | Complete | Invitation issuance, delivery, expiration, revocation, resend, and single-use token security. |
| `0.0.6` | Next | Invitation acceptance, browser account activation, verified email, and safe invalid/expired states. |
| `0.0.7` | Planned | Enumeration-safe password-reset request and completion with expiring tokens and session policy. |
| `0.0.8` | Planned | Session inventory/revocation, authentication audit events, login throttles, and recovery rate limits. |
| `0.0.9` | Planned | TOTP, recovery codes, recent reauthentication, privileged-role MFA enforcement, and secret-safe recovery flows. |
| `0.0.10` | Planned | Profile/security administration, secure production validation, and a tested OIDC provider boundary. |
| `0.0.11` | Planned | Authentication abuse suite, accessibility/browser remediation, operator documentation, and upgrade rehearsal. |
| `0.1.0` | Planned stabilization | Freeze the identity contract; close all authentication blockers and certify clean install/upgrade behavior. |

### `0.0.1` acceptance evidence

- [x] `make bootstrap` prepares local dependencies.
- [x] `make check` passes backend and frontend static/unit gates.
- [x] `make test-compose` proves a fresh production-shaped stack and health contract.
- [x] OpenAPI is generated and validated from backend source.
- [x] The React shell provides responsive sectioned navigation, client context, profile access, and administrative routes.
- [x] Markdown, authentication, envelope-encryption, and PDF choices have executable or documented feasibility evidence.
- [x] GitHub CI, Dependabot, CodeQL, secret scanning, dependency review, container scanning, and SBOM workflows are present.

Evidence: `docs/releases/0.0.1.md`. Hosted workflows remain unverified until the repository is published and a pull request runs.

### `0.0.2` acceptance criteria

- [x] A singleton installation record is created through a normal migration and locks first-owner creation transactionally.
- [x] Bootstrap status reveals no secret or submitted identity data.
- [x] Owner creation requires the deployment bootstrap secret and creates exactly one tenant and owner identity.
- [x] Missing/incorrect secrets, invalid input, concurrent/repeated claims, and ordinary public signup are denied and tested.
- [x] The bootstrap secret is generated locally, required by production validation, excluded from logs/responses, and documented for operators.
- [x] Migration, OpenAPI, Docker runtime, dependency, static-analysis, and secret-scanning gates pass.

Evidence: `docs/releases/0.0.2.md`.

### `0.0.3` acceptance criteria

- [x] The browser derives setup, sign-in, and authenticated states from server responses without exposing identity data before authentication.
- [x] First-owner setup is keyboard-accessible and responsive, never persists the deployment token or password, and establishes a normal Django session after success.
- [x] Sign-in and sign-out use maintained `django-allauth` headless endpoints with same-origin credentials and CSRF enforcement; missing/invalid CSRF and invalid credentials fail safely.
- [x] The application shell renders only after an authenticated server context succeeds and displays the actual owner/workspace identity.
- [x] Loading, validation, server-denial, retry, mobile, and sign-out failure states have unit, accessibility, and browser coverage.
- [x] OpenAPI, operator/security documentation, Docker runtime, Chromium, dependency, static-analysis, and secret-scanning gates pass.

Evidence: `docs/releases/0.0.3.md`.

### `0.0.4` acceptance criteria

- [x] The default Compose environment captures application mail in a pinned Mailpit container whose UI is bound only to the local host.
- [x] TekDocs-authored application mail uses Django's maintained SMTP backend through one multipart transactional-template service; callers do not construct ad hoc messages.
- [x] Production startup rejects a non-SMTP backend, missing host, invalid sender/port, partial credentials, conflicting TLS modes, or unacknowledged plaintext SMTP.
- [x] An operator command sends a non-sensitive delivery test and reports failures without printing recipient addresses, credentials, or message contents.
- [x] Unit and Docker tests prove text/HTML rendering, header/recipient validation, SMTP capture, and failure behavior.
- [x] Version, security/operator documentation, dependency scans, static analysis, secret scanning, and container gates agree at `0.0.4`.

Evidence: `docs/releases/0.0.4.md`.

### `0.0.5` acceptance criteria

- [x] Only the authenticated installation owner can list, issue, revoke, or resend tenant-scoped invitations; anonymous and unrelated authenticated users are denied.
- [x] Invitation tokens use maintained randomness, are stored only as digests, appear only in the email URL fragment, expire, rotate on resend, and become unusable after revocation.
- [x] Issuance prevents duplicate active invitations and existing-user invitations while allowing an expired invitation to be replaced safely.
- [x] Delivery uses the central multipart template service; failures retain a recoverable pending invitation without exposing its address or token in API errors, audits, or logs.
- [x] Invitation state changes create value-free append-only audit events and the API never returns token material.
- [x] Migration, OpenAPI, unit, PostgreSQL/Compose, mail-capture, authorization-negative, dependency, static-analysis, secret-scanning, and container gates pass at `0.0.5`.

Evidence: `docs/releases/0.0.5.md`.

## Entity and authorization foundation: `0.1.x` → `0.2.0`

| Release | Slice and exit condition |
| --- | --- |
| `0.1.1` | Tenant-scoped model/query primitives, organization scope contract, RLS strategy, and negative isolation harness. |
| `0.1.2` | Client/vendor/manufacturer/partner organizations with classifications and CRUD contracts. |
| `0.1.3` | People, employment/contact associations, sites, and locations. |
| `0.1.4` | Versioned custom-field definitions with JSON Schema validation and migration-safe values. |
| `0.1.5` | Typed entity links, backlinks, and permission-filtered search foundation. |
| `0.1.6` | Central policy service, permission catalog, built-in roles, and no inline role-name decisions. |
| `0.1.7` | Custom roles and tenant/client/collection-scoped assignments with MSP-private hard constraints. |
| `0.1.8` | Recycle bin/recovery, field-level cost visibility seam, and comprehensive IDOR/permission matrix. |
| `0.1.9` | Reference-dataset performance, migration rehearsal, API/UI accessibility, and isolation remediation. |
| `0.2.0` | Stabilize and certify the entity/RBAC subsystem; add no new domain family. |

## Reusable documentation: `0.2.x` → `0.3.0`

| Release | Slice and exit condition |
| --- | --- |
| `0.2.1` | Final Markdown dialect, server allowlist rendering, malicious corpus, and editor round-trip fixture gate. |
| `0.2.2` | Documents, stable blocks, ordered placements, WYSIWYG/raw/preview editing, and persistence. |
| `0.2.3` | Immutable block revisions, checksums, optimistic concurrency, history, and diff. |
| `0.2.4` | Live/pinned placement resolution, cycle prevention, and deterministic transclusion. |
| `0.2.5` | Backlinks, reuse-impact preview, permission-aware shared editing, detach, and entity mentions. |
| `0.2.6` | Policies/procedures/guides, templates, managed attachments, and Markdown import/export. |
| `0.2.7` | STATIC dependency resolution, canonical snapshot/manifest, digest, and Ed25519 signing. |
| `0.2.8` | Deterministic PDF artifacts, supersession/correction workflow, retention, and publication security corpus. |
| `0.2.9` | Documentation alpha stabilization, large-history performance, accessibility, upgrade, and backup evidence. |
| `0.3.0` | Stabilize and certify reusable documentation and immutable publication. |

## Credentials and inventory: `0.3.x` → `0.4.0`

| Release | Slice and exit condition |
| --- | --- |
| `0.3.1` | `SecretProvider` contract, PostgreSQL envelope-encrypted versions, associated data, and master-key validation. |
| `0.3.2` | Explicit reveal boundary, recent MFA, value-free audit, redaction, rewrap rotation, and backup failure tests. |
| `0.3.3` | Manufacturers/vendors, hardware models, and versioned specification definitions. |
| `0.3.4` | Hardware assets, serials, acquisition/disposal, warranty, assignment, and lifecycle history. |
| `0.3.5` | Software products, installations, licenses, seats, renewals, and relationships. |
| `0.3.6` | Costs and contracts with field-level permissions and non-disclosing list/search behavior. |
| `0.3.7` | Attachments, asset relationships, bulk operations, and safe file-processing corpus. |
| `0.3.8` | CSV import/export with dry-run, validation, idempotency, and secret-safe exclusions. |
| `0.3.9` | Inventory/vault stabilization, reference-data performance, restore, upgrade, and accessibility evidence. |
| `0.4.0` | Stabilize and certify encrypted credentials and hardware/software inventory. |

## Network inventory: `0.4.x` → `0.5.0`

| Release | Slice and exit condition |
| --- | --- |
| `0.4.1` | Racks, network devices, and physical/logical placement relationships. |
| `0.4.2` | VLANs, VRFs, subnets, CIDR validation, overlap policy, and property tests. |
| `0.4.3` | Addresses, interfaces, MAC records, assignments, and conflict detection. |
| `0.4.4` | Circuits, providers, handoffs, contracts, and lifecycle reminders. |
| `0.4.5` | Wireless networks and permission-aware DNS records. |
| `0.4.6` | Relationship-derived network diagrams and accessible tabular equivalents. |
| `0.4.7` | NetBox-compatible external identifiers plus deterministic import/reconciliation seam. |
| `0.4.8` | Network search/export, scale testing, upgrade/restore, and isolation remediation. |
| `0.5.0` | Stabilize and certify network inventory. |

## Client portal and notifications: `0.5.x` → `0.6.0`

| Release | Slice and exit condition |
| --- | --- |
| `0.5.1` | Explicit document publication states, audience projections, approvals, and withdrawal/supersession. |
| `0.5.2` | Client-user invitations, organization binding, portal session boundary, and isolation regression. |
| `0.5.3` | Read-only client document/reference browsing with unmistakable MSP-private/client-visible states. |
| `0.5.4` | Transactional event outbox, idempotent delivery jobs, and retry/dead-letter behavior. |
| `0.5.5` | In-app notification inbox and permission-filtered event payloads. |
| `0.5.6` | SMTP delivery, templates, bounce/failure handling, and redaction tests. |
| `0.5.7` | Notification preferences, batching, digests, and quiet-time behavior. |
| `0.5.8` | Document review/expiry reminders and calendar-feed seam. |
| `0.5.9` | Portal/notification stabilization, accessibility, mail-outage, load, and upgrade evidence. |
| `0.6.0` | Stabilize and certify controlled client access and notifications. |

## API and integrations: `0.6.x` → `0.7.0`

| Release | Slice and exit condition |
| --- | --- |
| `0.6.1` | `/api/v1` conventions, filtering/pagination/error/idempotency contracts, and generated TypeScript client. |
| `0.6.2` | Scoped personal/service tokens, rotation/revocation, expiry, and value-safe audit. |
| `0.6.3` | Signed outbound/inbound webhooks, replay defense, retries, and delivery inspection. |
| `0.6.4` | Integration provider contract and envelope-encrypted connection configuration. |
| `0.6.5` | Scheduled sync jobs, cursors, backoff, idempotency, and worker failure recovery. |
| `0.6.6` | Provider logs/metrics with secret redaction and bounded retention. |
| `0.6.7` | Conflict model and permission-aware reconciliation workflow; database remains canonical. |
| `0.6.8` | Deterministic sanitized Git export for selected non-secret documents/manifests. |
| `0.6.9` | Integration-runtime stabilization, webhook/SSRF abuse suites, upgrade, and load evidence. |
| `0.7.0` | Stabilize and certify the public API and integration framework. |

## Compliance and monitoring: `0.7.x` → `0.8.0`

| Release | Slice and exit condition |
| --- | --- |
| `0.7.1` | Compliance frameworks and versioned control catalogs. |
| `0.7.2` | Applicability, owners, status, reviews, and scoped control assignments. |
| `0.7.3` | Evidence links, collection windows, review history, and permission-aware reuse. |
| `0.7.4` | Risks, treatments, acceptance, deadlines, and reporting. |
| `0.7.5` | Immutable evidence bundles with manifests, digest, signing, and export. |
| `0.7.6` | Shared reminder schedules and calendar feeds for compliance and inventory deadlines. |
| `0.7.7` | Approved egress service with SSRF, redirect, DNS-rebinding, time, and size controls. |
| `0.7.8` | Domain RDAP/DNS monitoring and expiration/change notifications. |
| `0.7.9` | TLS certificate endpoint monitoring, chain/expiry evidence, and safe failure handling. |
| `0.7.10` | Compliance/monitoring stabilization, evidence integrity, accessibility, scale, and upgrade evidence. |
| `0.8.0` | Stabilize and certify compliance evidence and safe monitoring. |

## Public beta hardening: `0.8.x` → `0.9.0`

| Release | Slice and exit condition |
| --- | --- |
| `0.8.1` | Encrypted backup/restore tooling, separate-key recovery, and destructive-operation safeguards. |
| `0.8.2` | Upgrade rehearsal from every supported minor release and rollback/recovery runbooks. |
| `0.8.3` | WCAG 2.2 AA audit and remediation across critical workflows. |
| `0.8.4` | Localization readiness, timezone/locale correctness, and translatable UI contract. |
| `0.8.5` | Reference-dataset load/performance profiling and p95 remediation. |
| `0.8.6` | Chromium/Firefox/WebKit regression, responsive/device coverage, and browser artifact hygiene. |
| `0.8.7` | DAST, container/runtime hardening, dependency/license review, and abuse-suite remediation. |
| `0.8.8` | Operator, security, backup, upgrade, API, and end-user documentation completion. |
| `0.8.9` | External security review intake and resolution of all release-blocking findings. |
| `0.9.0` | Feature freeze and public beta; only fixes, hardening, and release evidence follow. |

## Release candidates: `0.9.x` → `1.0.0`

| Release | Slice and exit condition |
| --- | --- |
| `0.9.1` | Beta defect triage, dependency freeze policy, and zero unresolved Critical/untriaged High findings. |
| `0.9.2` | Clean-install and every-supported-version upgrade matrix on documented reference platforms. |
| `0.9.3` | Backup, restore, database recovery, key recovery, storage/mail outage, and worker retry rehearsal. |
| `0.9.4` | Signed release images, CycloneDX SBOMs, digests, attestations, and provenance dry run. |
| `0.9.5` | Final accessibility, performance, browser, DAST, and external-review remediation candidate. |
| `0.9.6` | Documentation freeze, release notes, support policy, final go/no-go packet, and release candidate. |
| `1.0.0` | Publish only after manual go/no-go approval; no new feature work enters this release. |

## Stretch lane and post-1.0 boundary

Read-only authenticated trust views, Snipe-IT read/reconciliation, NetBox read/reconciliation, richer Git remote export, and calendar feeds may enter an `0.x` patch only when its core gate remains green and the slice is explicitly rescheduled. Full appointment scheduling, bidirectional connector write-back, MDM connectors, SNMP monitoring, anonymous trust portals, ticketing/billing, and hosted multi-MSP control-plane work remain post-1.0.
