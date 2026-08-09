# Release Roadmap

The authoritative product scope is `docs/PRODUCT_CHARTER.md`. Patch releases are small, independently testable roadmap slices. Minor releases are stabilization checkpoints: they add no major capability and certify that the preceding patch line works as a coherent subsystem.

Most patch slices should fit one to three focused engineering sessions. A slice that grows beyond its stated exit condition must be split rather than silently expanded. Dates follow demonstrated velocity; security, migration, isolation, backup, and upgrade gates never compress to preserve a date.

Known limitations are release obligations, not informal notes. `docs/ENGINEERING_RISKS.md` records the reasoning, required solution, and owning milestone for every accepted concern; milestone closeout must disposition its assigned risk IDs.

## Release-line overview

| Stable release | Capability certified |
| --- | --- |
| `0.0.1` | Greenfield repository and delivery foundation. |
| `0.1.0` | Secure identity, authentication, owner administration, and tenant shell. |
| `0.2.0` | Addressable entities, selectable MSP/organization workspaces, scoped RBAC, and isolation. |
| `0.3.0` | Reusable Markdown documentation and immutable STATIC publication. |
| `0.4.0` | Encrypted credentials, supplier catalogs, and client hardware/software inventory. |
| `0.5.0` | Network inventory and relationship-derived views. |
| `0.6.0` | Controlled client portal, publication workflow, and notifications. |
| `0.7.0` | Stable integration API, provider runtime, webhooks, and reconciliation. |
| `0.8.0` | Compliance evidence plus domain inventory, renewal tracking, DNS observations, and safe certificate monitoring. |
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
| `0.0.6` | Complete | Invitation acceptance, browser account activation, verified email, and safe invalid/expired states. |
| `0.0.7` | Complete | Enumeration-safe password-reset request and completion with expiring tokens and session policy. |
| `0.0.8` | Complete | Session inventory/revocation, authentication audit events, login throttles, and recovery rate limits. |
| `0.0.9` | Complete | TOTP, recovery codes, recent reauthentication, privileged-role MFA enforcement, and secret-safe recovery flows. |
| `0.0.10` | Complete | Profile/security administration, secure production validation, and a tested OIDC provider boundary. |
| `0.0.11` | Complete | Authentication abuse suite, accessibility/browser remediation, operator documentation, and upgrade rehearsal. |
| `0.1.0` | Complete | Freeze the identity contract; close all authentication blockers and certify clean install/upgrade behavior. |

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

### `0.0.6` acceptance criteria

- [x] A pending, unexpired invitation can be accepted exactly once to create one active user, one verified primary allauth email, and one tenant membership.
- [x] Acceptance validates the password through Django, locks the invitation transactionally, clears its token digest, records its accepting user and timestamp, and emits a value-free audit event.
- [x] Missing, malformed, expired, revoked, accepted, mismatched, and concurrently reused tokens fail through one non-enumerating unavailable response without creating partial identity data.
- [x] The browser reads the token only from the invitation URL fragment, removes that fragment immediately, never persists the token or password, and establishes a normal CSRF-protected session after activation.
- [x] Valid, unavailable, password-validation, submitting, and completed activation states are responsive, keyboard accessible, and covered by unit and Chromium tests.
- [x] Public signup remains closed; invitation administration remains owner-only; migration, OpenAPI, Docker/PostgreSQL, browser, and security gates pass at `0.0.6`.

Evidence: `docs/releases/0.0.6.md`.

### `0.0.7` acceptance criteria

- [x] Sign-in exposes a responsive, keyboard-accessible password-recovery path with one request confirmation for known and unknown account addresses.
- [x] Reset issuance and completion use maintained allauth/Django primitives, CSRF protection, verified active accounts, and a configurable one-hour expiry by default.
- [x] Reset keys are delivered only in the email URL fragment, removed from browser history immediately, never persisted by the client, and rejected after expiry or first use.
- [x] Password completion applies Django validators, clears browser password fields on submission, does not auto-login, and invalidates all existing password-bound sessions.
- [x] Multipart request/change notifications use the central transactional email boundary without placing credentials or reset material in logs or response bodies.
- [x] Unit, Docker/PostgreSQL, Chromium, accessibility, dependency, static-analysis, secret-scanning, and container gates pass at `0.0.7`.

Evidence: `docs/releases/0.0.7.md`.

### `0.0.8` acceptance criteria

- [x] Authenticated users can open a visible, responsive Settings page to list their active browsers, identify the current session, refresh activity state, and revoke another session.
- [x] Session inventory and revocation use maintained allauth models and headless endpoints; records are restricted to the authenticated user, mutations require CSRF, and cross-user session IDs are denied.
- [x] Login success/failure, logout, password reset, session-client change, and explicit revocation produce append-only, tenant-associated authentication events without credentials or client/session identifiers in metadata.
- [x] Explicit login, failed-login, password-request, and reset-completion limits use a shared Valkey cache so policy remains consistent across web workers.
- [x] Unit and browser tests cover inventory, revocation, server denial, retry, CSRF, cross-user isolation, audit redaction, and rate-limit responses.
- [x] Migration, OpenAPI, Docker/PostgreSQL, accessibility, dependency, static-analysis, secret-scanning, and container gates pass at `0.0.8`.

Evidence: `docs/releases/0.0.8.md`.

### `0.0.9` acceptance criteria

- [x] Authenticated users can enroll a TOTP authenticator from a responsive Settings workflow, complete password login with TOTP or a single-use recovery code, and disable TOTP after recent password reauthentication.
- [x] TOTP secrets and recovery-code seeds use TekDocs envelope encryption before storage; the deployment master key remains outside PostgreSQL and a data migration encrypts legacy allauth MFA material.
- [x] Recovery codes are shown only at enrollment or replacement, disappear from browser state when acknowledged, are never included in email/audit metadata, and cannot be reused after successful authentication.
- [x] Recovery-code replacement and authenticator removal require recent allauth reauthentication; owner-only administrative APIs deny owners without an enrolled TOTP factor.
- [x] Enrollment, removal, reauthentication, MFA success/failure, and recovery reset create value-free append-only audit events and controlled security-notification email.
- [x] Unit, migration, Docker/PostgreSQL, Chromium, accessibility, CSRF, denial, dependency, static-analysis, secret-scanning, and container gates pass at `0.0.9`.

Evidence: `docs/releases/0.0.9.md`.

### `0.0.10` acceptance criteria

- [x] An authenticated installation member can edit their own display name from Settings; email remains read-only, invalid input is rejected, the shell updates immediately, and the change creates a value-free audit event.
- [x] Settings presents profile, two-factor, recovery-code, and active-session administration as one responsive security surface without weakening existing reauthentication or authorization boundaries.
- [x] OIDC is disabled by default and enabled only by one complete environment-supplied provider configuration; public provider discovery exposes only its stable identifier and display name, never client credentials or discovery internals.
- [x] OIDC login uses maintained allauth OpenID Connect redirect and state handling with issuer, audience, and signature validation; it admits only an existing invited account with a provider-verified matching email and leaves public account creation closed.
- [x] Production startup rejects partial or malformed OIDC configuration, insecure public/CSRF origins, disabled secure redirect/cookies, or inadequate HSTS while retaining the explicit localhost-only insecure public URL override used by the development Compose stack.
- [x] OpenAPI, unit, Docker/PostgreSQL, Chromium, accessibility, CSRF, denial, configuration-redaction, dependency, static-analysis, secret-scanning, and container gates pass at `0.0.10`.

Evidence: `docs/releases/0.0.10.md`.

### `0.0.11` acceptance criteria

- [x] A blocking authentication abuse suite covers account enumeration, CSRF bypass, invitation/reset/recovery replay, session isolation, MFA downgrade, audit redaction, and closed-signup/OIDC boundaries.
- [x] Critical bootstrap, invitation, password recovery, MFA, session, profile, OIDC, and sign-out browser journeys pass in Chromium, Firefox, and WebKit without detectable axe violations.
- [x] Pull requests retain a fast Chromium browser gate while scheduled and manually dispatched GitHub workflows run all three browser engines and retain per-engine failure artifacts.
- [x] An operator runbook documents initial authentication setup, invitation and recovery operations, MFA recovery, OIDC rollout, session response, protected secret handling, and safe troubleshooting.
- [x] A disposable, automated upgrade rehearsal starts from the supported `0.0.10` source, preserves representative identity/authentication data, applies current migrations, verifies invariants, and removes only its isolated resources.
- [x] Version, roadmap, OpenAPI, unit, PostgreSQL/Compose, three-engine browser, accessibility, upgrade, dependency, static-analysis, secret-scanning, and container evidence agree at `0.0.11`.

Evidence: `docs/releases/0.0.11.md`.

### `0.1.0` acceptance criteria

- [x] The documented bootstrap, invitation, password recovery, session, profile, MFA, audit, and OIDC boundaries are the frozen identity contract for the `0.1.x` line; the stabilization slice adds no new identity feature family.
- [x] MFA enrollment remains valid after recent reauthentication, exposes a locally generated QR code plus manual fallback, and loads safe recovery-code counts after refresh without invoking a protected code-reveal endpoint.
- [x] A disposable clean-install rehearsal starts every production-shaped service with new volumes, applies all migrations, reports the release version, and verifies the untouched one-time bootstrap state before removing only its isolated resources.
- [x] A disposable upgrade rehearsal preserves representative identity, membership, verified-email, password, encrypted-TOTP, and append-only audit data while upgrading the final `0.0.11` source to `0.1.0`.
- [x] Release metadata has a checked synchronization contract, while backend health and OpenAPI derive their version from installed package metadata rather than separate literals.
- [x] Roadmap, operator documentation, OpenAPI, unit, PostgreSQL/Compose, three-engine browser, accessibility, clean-install, upgrade, dependency, static-analysis, secret-scanning, and container evidence agree at `0.1.0`.

Evidence: `docs/releases/0.1.0.md`.

## Entity and authorization foundation: `0.1.x` → `0.2.0`

| Release | Status | Slice and exit condition |
| --- | --- | --- |
| `0.1.1` | Complete | Tenant-scoped model/query primitives, organization scope contract, RLS strategy, and negative isolation harness. |
| `0.1.2` | Complete | Client/vendor/manufacturer/partner organizations with classifications and CRUD contracts. |
| `0.1.3` | Complete | Routable organization profile and workspace-context API contract with explicit MSP/organization scope, deep links, safe creation defaults, and closure of `TD-RISK-003`, `005`, `011`, and `016`; document the `TD-RISK-004` and `007` deployment plans. |
| `0.1.4` | Complete | Searchable, bounded workspace switcher, MSP return, classification-aware navigation, independent-tab history, stale-data isolation, and `TD-RISK-012`. |
| `0.1.5` | Complete | People plus employment/contact associations in MSP and organization workspaces. |
| `0.1.6` | Complete | Sites and hierarchical locations with MSP/organization ownership, structured People placement, workspace-aware navigation, and PostgreSQL integrity guards. |
| `0.1.7` | Complete | Versioned MSP-wide and organization-specific custom-field definitions with JSON Schema validation, migration-safe values, and Site/Location value entry. |
| `0.1.8` | Complete | Typed entity links, backlinks, organization relationships, and permission-filtered search foundation. |
| `0.1.9` | Complete | Central policy service, permission catalog, built-in roles, organization access modes (`all authorized MSP staff` or `assigned staff only`), no inline role-name decisions, and the first half of `TD-RISK-001`. |
| `0.1.10` | Complete | Explicit per-client MSP staff assignments, assigned-only policy composition, assignment administration, and the next bounded portion of `TD-RISK-001`. |
| `0.1.11` | Complete | Custom role definitions plus tenant- and organization-scoped role assignments without inline permission logic. |
| `0.1.12` | Complete | Organization access collections, collection-scoped custom-role assignments, MSP-private Entity constraints, and the field-level cost visibility seam that completes `TD-RISK-001` implementation. |
| `0.1.13` | Complete | Workspace-scoped recycle-bin recovery, database-enforced audit immutability (`TD-RISK-008`), and comprehensive IDOR/permission matrix. |
| `0.1.14` | Planned | Active runtime-role RLS (`TD-RISK-002`), reproducible Python/runtime inputs (`TD-RISK-009`), and hosted-automation evidence when authorized (`TD-RISK-010`). |
| `0.1.15` | Planned | Reference performance, migration, accessibility, workspace, authorization, and isolation stabilization. |
| `0.2.0` | Planned | Stabilize and certify the entity/RBAC subsystem; add no new domain family. |

### `0.1.1` acceptance criteria

- [x] Tenant-owned domain reads have one explicit manager contract that refuses an omitted tenant and supports immutable tenant and organization data scopes.
- [x] A minimal organization scope anchor attaches to a stable MSP-owned entity; classifications, CRUD, and navigation remain in `0.1.2`.
- [x] Entity, organization, entity-link, invitation, and membership access paths use or expose the scoped query boundary, while pre-authentication token resolution remains a documented narrow exception.
- [x] PostgreSQL enforces same-tenant organization/entity/link relationships and exposes transaction-local RLS scope functions that deny missing, cross-tenant, and cross-organization context.
- [x] ADR 0006 documents the non-owner runtime role, `USING`/`WITH CHECK`, pooled-connection safety, token redemption, worker, migration, and activation requirements; active RLS protection is not claimed early.
- [x] `make test-isolation` and the Compose CI job run the PostgreSQL negative-isolation harness; migration, static, unit, runtime, and version gates agree at `0.1.1`.

Evidence: `docs/releases/0.1.1.md`.

### `0.1.2` acceptance criteria

- [x] Every organization remains attached to one stable MSP-scoped Entity and may hold any unique combination of client, vendor, manufacturer, and partner classifications.
- [x] The tenant-scoped API lists and reads active organizations and transactionally creates, updates, and archives them without accepting tenant or entity ownership from the browser.
- [x] Organization administration is restricted through the existing owner/MFA policy boundary until the permission catalog and role assignments arrive; anonymous, non-owner, missing-MFA, CSRF, and cross-tenant cases fail safely.
- [x] PostgreSQL rejects cross-tenant classification writes, while organization changes produce value-free append-only audit events.
- [x] The Organizations page provides responsive loading, empty, filtered, create, edit, archive-confirmation, denial, and accessibility states using the established TekDocs shell.
- [x] Version, migration, OpenAPI, static, unit, PostgreSQL/Compose, browser, clean-install, upgrade, and security evidence agree at `0.1.2`.

Evidence: `docs/releases/0.1.2.md`.

### Workspace conformance rule

Beginning with `0.1.3`, every domain family must declare whether each record is MSP-owned, organization-owned, or an explicitly permission-aware reference. List, detail, create, update, archive, search, export, notification, and worker paths must resolve the same URL-derived workspace context and include cross-workspace negative tests. Selecting a workspace changes presentation and scope; it never grants access.

Organization classifications are additive capabilities. A business classified as both vendor and manufacturer has one identity and one workspace with the authorized union of supplier features. Client workspaces eventually expose client-owned people, documentation, assets, networks, vendors derived from asset relationships, and other scoped data. Supplier workspaces eventually expose contacts, product/model templates, and supplier-owned documentation that retains provenance when instantiated for a client.

### `0.1.5` acceptance criteria

- [x] A person has one tenant-wide entity identity and one or more scoped employment/contact associations; relationship fields do not become authorization roles.
- [x] MSP People lists only MSP-scoped associations, while organization People lists only associations belonging to the URL-selected authorized organization.
- [x] Owner-plus-MFA CRUD supports full and preferred name, relationship type, role/responsibility, location label, office, phone, and email; mutations derive scope from the route and emit value-free audit events.
- [x] The list supports bounded server-side all-field search, field filtering, allowed-field sorting, and pagination. Users can choose visible columns with a keyboard-accessible settings control whose non-sensitive preference is stored locally.
- [x] Loading, empty, error, denial, stale-workspace, responsive, keyboard, and accessibility behavior is covered. Cross-tenant and cross-organization reads and mutations fail without revealing record existence.
- [x] PostgreSQL rejects mismatched tenant/person/organization associations through a database constraint or trigger, and migration, OpenAPI, Docker, unit, component, browser, isolation, clean-install, upgrade, and security evidence agree at `0.1.5`.
- [x] ADR 0008 documents how future user identities, client assignment modes, custom roles, sites, and shared-person attachment extend this model without treating job titles as permissions.

Evidence: `docs/releases/0.1.5.md`.

### `0.1.6` acceptance criteria

- [x] Sites and locations have stable Entity identities and belong to exactly one MSP or organization workspace; nested locations remain within one site and workspace.
- [x] Owner-plus-MFA CRUD supports site address/contact metadata and hierarchical building, floor, suite, room, office, desk, and area locations with value-free audit events and safe archival.
- [x] MSP and organization Sites routes resolve ownership exclusively from their URL-derived workspace, clear stale-workspace data, and reject cross-tenant or cross-organization reads and mutations without revealing record existence.
- [x] People associations may optionally reference an active structured site and location from the same workspace. Existing free-text location/office labels remain available and are retained as display snapshots when structured references are assigned or later archived.
- [x] PostgreSQL guards reject mismatched tenant, organization, entity, site, location-parent, and Person-association placement relationships even if application scoping is bypassed.
- [x] Responsive, keyboard, loading, empty, error, hierarchy, cycle, denial, accessibility, migration, OpenAPI, Docker/PostgreSQL, browser, clean-install, upgrade, and security evidence agree at `0.1.6`.

ADR 0009 defines the site/location hierarchy and retained-label contract.

ADR 0007 defines the workspace-context boundary.

Evidence: `docs/releases/0.1.6.md`.

### `0.1.7` acceptance criteria

- [x] A stable custom-field definition belongs to the MSP or exactly one organization and targets one Entity type. Its key, target type, and ownership scope cannot be silently reinterpreted.
- [x] Creating or editing a definition produces an immutable, sequential version containing its label, help text, required flag, field type, and server-generated JSON Schema. Prior versions remain readable.
- [x] Supported text, integer, number, boolean, date, URL, email, choice, and multi-choice values validate through a maintained JSON Schema implementation; arbitrary executable schemas and secret field types are not accepted.
- [x] Entity values record the exact definition version that validated them. Publishing an incompatible definition version preserves old values, reports migration impact, and requires an explicit later edit rather than rewriting or discarding data.
- [x] MSP-wide definitions are inherited by matching organization-owned entities. Organization definitions apply only inside their owning workspace and cannot be edited from another organization or through the MSP definition route.
- [x] Route-derived APIs and PostgreSQL guards reject cross-tenant, cross-organization, wrong-entity-type, wrong-definition-version, malformed-envelope, and archived-definition writes without exposing record existence or field values in audit events.
- [x] The Custom Fields interface manages definitions and version history in MSP and organization contexts. Site and Location records provide the first responsive, keyboard-accessible value-entry workflow with loading, empty, validation, stale-version, denial, and stale-workspace states.
- [x] Migration, OpenAPI, Docker/PostgreSQL, unit, component, browser, clean-install, preserved-data upgrade, security, and real browser-to-database evidence agree at `0.1.7`.

ADR 0010 defines definition ownership, immutable versions, inherited applicability, and version-pinned Entity value envelopes.

Evidence: `docs/releases/0.1.7.md`.

### `0.1.8` acceptance criteria

- [x] Entity links use a maintained, bounded type catalog with explicit forward/inverse labels and symmetric-link behavior. Arbitrary relationship types, self-links, duplicate links, caller-supplied ownership, and caller-supplied metadata are rejected.
- [x] Link endpoints retain stable Entity identities and exact tenant ownership. PostgreSQL guards reject cross-tenant endpoints and immutable identity changes even if application scoping is bypassed.
- [x] A route-derived link API lists outgoing relationships and incoming backlinks for one authorized Entity, creates a permitted relationship, and archives it without disclosing inaccessible endpoint existence or relationship metadata.
- [x] Bounded entity search is resolved through one workspace-aware visibility service before filtering or pagination. MSP scope returns only MSP-owned records; organization scope returns that organization's records, its own anchor, and explicitly eligible active organization anchors for organization relationships.
- [x] Search results disclose only stable ID, display name, Entity type, owning-workspace label, and relationship eligibility. Archived, foreign-tenant, sibling organization-owned, malformed, over-broad, and unauthorized searches fail or remain absent.
- [x] Organization records expose their typed relationships and reverse backlinks. The first UI supports searching eligible organizations, adding a bounded relationship, following an authorized organization target, and archiving a relationship with responsive, keyboard, loading, empty, error, denial, and stale-workspace states.
- [x] Relationship mutations remain installation-owner-plus-MFA operations until `0.1.9`–`0.1.10`; audit events are value-free, and search/link APIs share the workspace resolver rather than inferring authorization from submitted Entity IDs.
- [x] Migration, OpenAPI, Docker/PostgreSQL, unit, component, browser, clean-install, preserved-data upgrade, security, and real browser-to-database evidence agree at `0.1.8`.

ADR 0011 defines the typed-link catalog, direction, visibility, backlink, archival, and scoped-search contracts.

Evidence: `docs/releases/0.1.8.md`.

### `0.1.9` acceptance criteria

- [x] One maintained permission catalog defines stable keys, descriptions, and MFA requirements for every implemented read and mutation. Views, workspace resolvers, workers, and services make no role-name authorization decisions outside the central policy service.
- [x] Owner, Administrator, Technician, Contributor, Read-only, Client Administrator, and Client User have documented built-in definitions. Owner remains an immutable installation identity; tenant memberships use only tenant-assignable roles, while client roles are reserved for the scoped assignments delivered in `0.1.10`.
- [x] Existing and newly accepted tenant memberships migrate to least-privilege Read-only access. An owner-plus-MFA API lists members and changes tenant-assignable built-in roles without allowing owner reassignment, self-escalation, cross-tenant changes, arbitrary role values, or role metadata from the browser.
- [x] Each organization has an explicit `all_authorized` or `assigned_only` MSP-staff access mode. `all_authorized` still requires the relevant permission; `assigned_only` fails closed for non-owners until user-to-organization assignments arrive in `0.1.10`.
- [x] Organization lists, switcher search, direct workspace resolution, domain APIs, entity search, and relationship backlinks apply the same policy-filtered organization boundary. Selection, a guessed UUID, an MSP-wide role, or a related EntityLink cannot bypass the access mode.
- [x] Privileged permissions require enrolled TOTP through the policy service. Read-only role changes and hidden controls never replace server authorization, and denials disclose no inaccessible organization or membership data.
- [x] A restrained Access Control interface shows built-in role definitions, tenant members, and organization access modes with responsive, keyboard, loading, empty, error, denial, confirmation, and stale-response behavior.
- [x] Allow/deny, missing-MFA, CSRF, cross-tenant, cross-client, access-mode, role-escalation, migration, OpenAPI, Docker/PostgreSQL, unit, component, browser, clean-install, preserved-data upgrade, security, and real browser-to-database evidence agree at `0.1.9`.

ADR 0012 defines the permission catalog, policy decision contract, built-in-role boundary, MFA enforcement, and staged organization assignment model.

Evidence: `docs/releases/0.1.9.md`.

### `0.1.10` acceptance criteria

- [x] A tenant-scoped organization staff assignment joins exactly one active tenant membership to exactly one organization; duplicate, owner, cross-tenant, missing-member, and malformed assignments fail safely.
- [x] PostgreSQL guards enforce that assignment, membership, and organization share one tenant even when application services are bypassed. Assignment identity and ownership are immutable; removal is explicit and auditable.
- [x] The central policy service treats assignment as an additional access-mode condition, never as a permission grant. A member still needs the relevant tenant-role permission and MFA where required.
- [x] `assigned_only` organizations are visible and routable to explicitly assigned MSP staff across lists, switcher search, direct workspace resolution, domain APIs, entity search, and relationship backlinks. Unassigned sibling and foreign-tenant records remain non-disclosing.
- [x] Owner-plus-MFA APIs list, add, and remove organization staff assignments using stable user and organization identifiers, scoped lookups, value-free audit events, CSRF protection, and idempotent retry behavior.
- [x] The Access Control interface manages assigned staff without implying that assignment changes a tenant role. It includes responsive, keyboard, loading, empty, error, denial, confirmation, and stale-response behavior.
- [x] Client Administrator and Client User remain cataloged organization-scoped roles but are not assigned to MSP tenant members in this slice. Custom roles and broader scoped role composition remain `0.1.11`–`0.1.12`.
- [x] Allow/deny, permission-plus-assignment composition, missing-MFA, CSRF, cross-tenant, cross-client, guessed-ID, database-guard, migration, OpenAPI, Docker/PostgreSQL, unit, component, browser, clean-install, preserved-data upgrade, security, and real browser-to-database evidence agree at `0.1.10`.

ADR 0013 defines explicit MSP staff assignments, policy composition, retained owner break-glass access, and the staged custom-role boundary.

Evidence: `docs/releases/0.1.10.md`.

### `0.1.11` acceptance criteria

- [x] Tenant-owned custom roles have stable identity, one immutable tenant or organization assignment scope, a unique bounded name, description, normalized maintained-catalog permissions, and archival rather than destructive deletion.
- [x] Custom permissions are additive to one built-in tenant role. Tenant assignments apply throughout already-reachable workspaces; organization assignments apply only to the exact organization and never create or bypass an organization staff assignment.
- [x] A centralized custom-assignable permission allowlist excludes ownership, access-control administration, secret access, and cost visibility. Catalog MFA requirements apply identically to built-in and custom grants.
- [x] Owner-plus-MFA APIs create, edit, list, and archive custom roles and add, list, and remove tenant/organization assignments using scoped lookups, explicit confirmation, value-free audit events, and non-disclosing errors.
- [x] PostgreSQL guards reject cross-tenant role permissions and assignments, scope/organization mismatches, owner assignments, arbitrary permission keys, duplicate assignments, and immutable identity changes when application services are bypassed.
- [x] The Access Control interface exposes restrained role-definition and scoped-assignment workflows with responsive, keyboard, loading, empty, validation, denial, confirmation, and stale-response states.
- [x] Built-in-only behavior remains unchanged when no custom assignments exist. Allow/deny, additive composition, access-mode separation, missing-MFA, CSRF, cross-tenant, cross-client, guessed-ID, migration, OpenAPI, Docker/PostgreSQL, unit, component, browser, clean-install, preserved-data upgrade, and security evidence agree at `0.1.11`.

ADR 0014 defines additive custom roles, scope composition, custom-assignable permissions, and the independent organization-reachability boundary.

Evidence: `docs/releases/0.1.11.md`.

### `0.1.12` acceptance criteria

- [x] Tenant-owned access collections group exact active organizations for authorization only; they have stable identity, normalized unique names, descriptions, explicit membership changes, archival, and no document-folder or generic-entity semantics.
- [x] Collection-scoped custom roles add permissions only for active member organizations. They never create or bypass an `assigned_only` staff-access edge, and collection membership changes take effect immediately without rewriting assignments.
- [x] Owner-plus-MFA and CSRF-protected APIs and UI manage collections, organization membership, collection-scoped role definitions, and assignments through scoped identifiers, confirmation, non-disclosing failures, and value-free audit events.
- [x] Every Entity receives a deny-by-default `msp_private` or explicit `client_visible` classification. The central audience policy treats `msp_private` as a hard constraint that no role grant can override and requires exact organization scope for future client-portal projections.
- [x] `costs.view` is enforced through a central field-policy projection seam, omitted rather than nulled when denied, and may be delegated through tenant, exact-organization, or collection custom roles without granting any unrelated sensitive field.
- [x] PostgreSQL guards reject cross-tenant collection membership/assignments, scope-target mismatches, owner assignments, invalid visibility values, duplicate edges, archived targets, and immutable identity changes when application services are bypassed.
- [x] Built-in-only and earlier tenant/organization role behavior remains unchanged. Allow/deny, collection composition, access-mode separation, MSP-private precedence, cost-field omission, MFA, CSRF, guessed-ID, cross-tenant/client, migration, OpenAPI, Docker/PostgreSQL, component, browser, clean-install, upgrade, and security evidence agree at `0.1.12`.

ADR 0015 defines access-collection semantics, audience visibility precedence, and field-policy projection.

Evidence: `docs/releases/0.1.12.md`.

### `0.1.13` acceptance criteria

- [x] MSP and active organization workspaces expose one bounded recycle-bin API for archived organizations, person associations, sites, location subtrees, and custom-field definitions. Results disclose only records in the exact authorized workspace and include stable type, identifier, display label, archive time, and cascade count.
- [x] Recovery requires the central `recycle_bin.restore` permission, MFA, and the record type's existing archive/manage permission. Tenant scope, organization reachability, `assigned_only`, custom-role scope, and non-disclosing identifier resolution remain hard constraints; CSRF protects every recovery mutation.
- [x] Site and location recovery restores only records archived in the same cascade, preserves intentionally older archive state, and refuses missing or archived dependencies. Conflicts and stale requests fail atomically without partial recovery or value-bearing audit metadata.
- [x] Audit events are insert-only in PostgreSQL. Database triggers reject ORM queryset, bulk, raw-SQL, and cascade update/delete attempts while ordinary inserts remain available; the application exposes no audit retention bypass.
- [x] A maintained route/permission inventory drives a blocking IDOR matrix across every implemented authenticated API family. Anonymous, insufficient-permission, missing-MFA, CSRF, malformed/guessed identifier, cross-tenant, sibling-client, and assigned-only bypass cases are covered where applicable without treating frontend visibility as authorization.
- [x] The shell exposes a restrained, keyboard-accessible recycle-bin list in MSP and organization context with bounded search/type filters, loading, empty, denial, conflict, confirmation, recovery, responsive, and stale-workspace states.
- [x] Existing list/detail/archive behavior remains unchanged. Migration, OpenAPI, Docker/PostgreSQL, unit, component, browser, real-stack, clean-install, preserved-data upgrade, security, and permission/IDOR evidence agree at `0.1.13`.

ADR 0016 defines the recoverable-record boundary, cascade semantics, database audit immutability, and route-matrix certification contract.

Evidence: `docs/releases/0.1.13.md`.

### `0.1.3` acceptance criteria

- [x] Clicking an active organization title opens a stable organization workspace overview route; refreshing or sharing that route restores the same authorized context.
- [x] One server-owned resolver returns either the MSP workspace or an authorized organization workspace with stable identity, display name, classifications, and available domain capabilities without accepting tenant ownership from the browser.
- [x] Workspace-aware APIs derive organization ownership for creates and require the same tenant-plus-organization scope for reads and mutations; a selected identifier never grants permission.
- [x] MSP-owned organization anchors remain discoverable from the MSP workspace while organization-owned child records cannot leak into MSP-only or sibling-organization queries except through an explicit reference contract.
- [x] Missing, archived, cross-tenant, unauthorized, malformed, and mismatched workspace identifiers fail without disclosing organization data and receive API/negative-isolation coverage.
- [x] This slice supplies the route, overview, and context contract; the searchable shell switcher remains `0.1.4` scope.
- [x] A maintained routing boundary replaces pathname conditionals; an isolated non-mocked browser journey proves owner bootstrap, MFA, organization creation, record click, context resolution, and PostgreSQL-backed drill-in (`TD-RISK-003`, `TD-RISK-011`).
- [x] Local Compose provenance is checked and normalized without deleting persistent data, and local frontend gates enforce or supply Node 24 (`TD-RISK-005`, `TD-RISK-016`).
- [x] The secret-file injection and exact production-image rehearsal plans document owners, failure behavior, test gates, and later enforcement milestones (`TD-RISK-004`, `TD-RISK-007`).

Evidence: `docs/releases/0.1.3.md`.

### `0.1.4` acceptance criteria

- [x] The shell workspace control opens a keyboard-accessible searchable list of authorized client, vendor, manufacturer, and partner organizations plus a persistent MSP-workspace entry.
- [x] Selecting an organization from its record or switcher updates the workspace name, all applicable classification labels, navigation capabilities, page title/breadcrumb context, and URL; multi-classified organizations receive the authorized union of capabilities.
- [x] Navigation preserves the active workspace when moving among available areas, while returning to the MSP workspace preserves the equivalent top-level route when one exists.
- [x] Switching clears prior-workspace content before loading, ignores late responses from the old context, and never stores organization selection as authorization-bearing session state.
- [x] Browser history, bookmarks, refreshes, mobile navigation, and separate tabs remain independent and deterministic.
- [x] Component and browser tests cover search, empty/no-access states, keyboard behavior, direct organization drill-in, MSP return, stale-response isolation, cross-workspace denial, and accessibility.

Evidence: `docs/releases/0.1.4.md`.

The maintained MSP/client/supplier route and navigation matrix is `docs/INFORMATION_ARCHITECTURE.md`. Areas shown before their domain milestone are explicit scope-aware placeholders, not implemented record stores. Ticketing and accounting remain post-`1.0` even though their eventual context is reserved in the navigation contract.

## Reusable documentation: `0.2.x` → `0.3.0`

| Release | Slice and exit condition |
| --- | --- |
| `0.2.1` | Final Markdown dialect, server allowlist rendering, malicious corpus, editor round-trip fixture gate, and explicit disposition of `TD-RISK-014`. |
| `0.2.2` | Workspace-aware title-first Documentation indexes, MSP/client document ownership scopes, permission-aware cross-listing references, stable blocks, ordered placements, WYSIWYG/raw/preview editing, and persistence. Live titles open the authorized editor while STATIC publication titles open immutable output. |
| `0.2.3` | Immutable block revisions, checksums, optimistic concurrency, history, and diff. |
| `0.2.4` | Live/pinned placement resolution, cycle prevention, and deterministic transclusion. |
| `0.2.5` | Backlinks, reuse-impact preview across client listings, permission-aware shared editing, detach, and entity mentions. |
| `0.2.6` | Policies/procedures/guides, templates, managed attachments, and Markdown import/export. |
| `0.2.7` | STATIC dependency resolution, canonical snapshot/manifest, digest, and Ed25519 signing. |
| `0.2.8` | Deterministic PDF artifacts, supersession/correction workflow, retention, and publication security corpus. |
| `0.2.9` | Documentation alpha stabilization, editor chunk/performance remediation (`TD-RISK-013`), large-history performance, accessibility, upgrade, and backup evidence. |
| `0.3.0` | Stabilize and certify reusable documentation and immutable publication. |

## Credentials and inventory: `0.3.x` → `0.4.0`

| Release | Slice and exit condition |
| --- | --- |
| `0.3.1` | `SecretProvider` contract, PostgreSQL envelope-encrypted versions, associated data, master-key validation, and secret-file injection implementation from `TD-RISK-004`. |
| `0.3.2` | Explicit reveal boundary, recent MFA, value-free audit, redaction, rewrap rotation, and backup failure tests. |
| `0.3.3` | Supplier-workspace product/model catalogs, hardware/software template identity, and versioned specification definitions. |
| `0.3.4` | Supplier-owned product documentation, client asset instantiation with retained product/specification/document provenance, and relationship-derived client vendor lists. |
| `0.3.5` | Client hardware assets, serials, acquisition/disposal, warranty, assignment, and lifecycle history. |
| `0.3.6` | Software installations, licenses, seats, renewals, and relationships. |
| `0.3.7` | Costs and contracts with field-level permissions and non-disclosing list/search behavior. |
| `0.3.8` | Attachments, asset relationships, bulk operations, and safe file-processing corpus. |
| `0.3.9` | CSV import/export with dry-run, validation, idempotency, and secret-safe exclusions. |
| `0.3.10` | Inventory/vault stabilization, workspace/reference-data performance, restore, upgrade, and accessibility evidence. |
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
| `0.6.6` | Maintained structured logging plus provider logs/metrics with field allowlists, secret redaction, bounded retention, and `TD-RISK-015`. |
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
| `0.7.8` | Workspace-owned registered-domain inventory with normalized names, registrar/provider, registration and expiration dates, renewal mode, responsible owner, status, notes, and Entity relationships. |
| `0.7.9` | Domain hierarchy for managed subdomains and hostnames, DNS record observations, explicit discovery provenance, and duplicate/cycle protection. |
| `0.7.10` | Renewal/expiration schedules, review state, reminder events, notification/calendar integration, and stale or conflicting source handling. |
| `0.7.11` | Safe RDAP and authoritative-DNS collection through the approved egress service, with observed-vs-entered reconciliation and expiration/change notifications. |
| `0.7.12` | TLS endpoint inventory related to domains/hostnames, protocol-aware validation, leaf/chain/hostname/trust/expiry evidence, scan history, and safe failure handling. |
| `0.7.13` | Domain/certificate stabilization, IDN normalization, wildcard/SAN coverage, DNSSEC/CAA observations, evidence integrity, accessibility, scale, isolation, and upgrade evidence. |
| `0.8.0` | Stabilize and certify compliance evidence and safe monitoring. |

## Public beta hardening: `0.8.x` → `0.9.0`

| Release | Slice and exit condition |
| --- | --- |
| `0.8.1` | Encrypted backup/restore tooling, separate-key recovery, destructive-operation safeguards, and implementation of `TD-RISK-006`. |
| `0.8.2` | Upgrade rehearsal from every supported minor release and rollback/recovery runbooks. |
| `0.8.3` | WCAG 2.2 AA audit and remediation across critical workflows. |
| `0.8.4` | Localization readiness, timezone/locale correctness, and translatable UI contract. |
| `0.8.5` | Reference-dataset load, editor bundle/device performance (`TD-RISK-013`), profiling, and p95 remediation. |
| `0.8.6` | Chromium/Firefox/WebKit regression, responsive/device coverage, and browser artifact hygiene. |
| `0.8.7` | DAST, secret-file enforcement (`TD-RISK-004`), production runtime/migration hardening (`TD-RISK-007`), pinned supply-chain inputs (`TD-RISK-009`), structured-log review (`TD-RISK-015`), dependency/license review, and abuse-suite remediation. |
| `0.8.8` | Operator, security, backup, upgrade, API, and end-user documentation completion. |
| `0.8.9` | External security review intake and resolution of all release-blocking findings. |
| `0.9.0` | Feature freeze and public beta; only fixes, hardening, and release evidence follow. |

## Release candidates: `0.9.x` → `1.0.0`

| Release | Slice and exit condition |
| --- | --- |
| `0.9.1` | Beta defect triage, dependency freeze policy, and zero unresolved Critical/untriaged High findings. |
| `0.9.2` | Clean-install and every-supported-version upgrade matrix on documented reference platforms. |
| `0.9.3` | Backup, restore, database recovery, key recovery, storage/mail outage, worker retry rehearsal, and final closure evidence for `TD-RISK-006`. |
| `0.9.4` | Signed exact production images, CycloneDX SBOMs, digests, attestations, provenance, and final closure evidence for `TD-RISK-007` and `TD-RISK-009`. |
| `0.9.5` | Final accessibility, performance, browser, DAST, and external-review remediation candidate. |
| `0.9.6` | Documentation freeze, release notes, support policy, final go/no-go packet, and release candidate. |
| `1.0.0` | Publish only after manual go/no-go approval; no new feature work enters this release. |

## Stretch lane and post-1.0 boundary

Read-only authenticated trust views, Snipe-IT read/reconciliation, NetBox read/reconciliation, richer Git remote export, and calendar feeds may enter an `0.x` patch only when its core gate remains green and the slice is explicitly rescheduled. Full appointment scheduling, bidirectional connector write-back, MDM connectors, SNMP monitoring, anonymous trust portals, ticketing/billing, and hosted multi-MSP control-plane work remain post-1.0.
