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
| `0.4.0` | External credential references, supplier catalogs, and MSP/client operational inventory. |
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
| `0.1.14` | Complete | Active non-owner runtime-role RLS for the implemented domain boundary (`TD-RISK-002`), reproducible Python/runtime inputs (`TD-RISK-009`), and an explicit externally blocked disposition for hosted-automation evidence (`TD-RISK-010`). |
| `0.1.15` | Complete | Reference performance, migration, accessibility, workspace, authorization, and isolation stabilization. |
| `0.2.0` | Complete | Certify the entity/RBAC subsystem, close control-plane scope-integrity gaps, and add no new domain family. |

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

### `0.1.14` acceptance criteria

- [x] Compose separates the PostgreSQL migration owner from a fixed, provisioned application runtime role. Web, worker, and scheduler use the runtime credential; only the one-shot migration service receives owner credentials and schema-changing authority.
- [x] Production validation rejects a runtime connection that owns application tables, is superuser, has `BYPASSRLS`, or is not the configured runtime role. Runtime startup also verifies that the expected policy inventory is active.
- [x] Every currently implemented core tenant-owned table has forced PostgreSQL RLS under the runtime role. Direct organization-owned tables enforce exact MSP/organization scope with `USING` and `WITH CHECK`; tenant-wide registry/control records enforce the exact tenant. Authentication-provider tables and the tenant authorization control plane remain outside organization RLS and retain the central policy boundary pending final `0.2.0` certification.
- [x] Authenticated session requests run in one atomic boundary, derive the installation tenant server-side, and bind transaction-local scope before domain access. After Django's CSRF view check, organization routes resolve the URL workspace inside that tenant and rebind its exact database scope; each view then applies the central policy service before returning data or mutating state. Anonymous bootstrap and invitation acceptance bind only after their tenant is established.
- [x] Runtime-role tests prove missing-scope denial, raw-SQL cross-tenant and sibling-organization denial, write denial through `WITH CHECK`, inability to mutate schema, exact organization operation, authorized MSP operation, and pooled-connection scope cleanup. Worker and management-command helpers fail closed without an explicit scope.
- [x] Python production and development dependencies resolve from reviewed hash-locked files. Backend, frontend, database, cache, mail, browser, scanner, and release base images are digest pinned; GitHub Actions use immutable commit SHAs with update annotations and Dependabot remains configured.
- [x] Local workflow linting and the complete release gate agree at `0.1.14`. Hosted CodeQL, dependency review, browser matrix, artifact, and branch-protection evidence is either retained from an authorized published run or recorded as externally blocked without being represented as verified.

ADR 0017 defines runtime/migration role separation, request and worker scope binding, the initial active-policy inventory, and the supply-chain reproducibility boundary.

Evidence: `docs/releases/0.1.14.md`.

### `0.1.15` acceptance criteria

- [x] A deterministic PostgreSQL reference fixture covers 100 organizations and at least 10,000 implemented entities. Workspace discovery, organization listing, People listing/search, Sites listing, and relationship discovery retain bounded query counts as result pages and unrelated tenant/client data grow; ordinary indexed reads remain below the documented 500 ms p95 target on the local Docker reference environment.
- [x] A blocking migration-cycle rehearsal creates representative tenant, organization, person, site/location, custom-field, relationship, role/assignment, archive, and audit data; reverses and reapplies the latest reversible isolation migration; and proves row counts, stable identifiers, RLS inventory, audit immutability, and runtime-role restrictions are preserved. Fresh-install and the supported `0.1.3` upgrade rehearsals remain green.
- [x] Automated axe coverage includes every currently implemented MSP and organization workflow plus workspace-unavailable and capability-denied states. Keyboard-only tests cover navigation opening/closing, workspace search, Escape focus restoration, route switching, dialogs, and data-table controls in Chromium, Firefox, and WebKit.
- [x] Workspace regression tests certify direct links, refresh, back/forward history, mobile switching, rapid stale-response cancellation, client-only search while in client context, capability-derived navigation, and safe handling of unsupported or unauthorized organization areas without leaking workspace data.
- [x] The authenticated-route inventory, permission matrix, custom-role/collection/assigned-only suites, sensitive-field/audience constraints, recycle recovery, append-only audit behavior, and raw runtime-role RLS matrix pass together against PostgreSQL. Query optimization or caching may not weaken policy filtering or database scope.
- [x] OpenAPI, architecture, threat model, security guidance, performance/migration runbooks, engineering risks, and release evidence agree at `0.1.15`; the complete Docker-backed release gate passes with no unresolved stabilization blocker. Hosted workflow execution remains externally blocked unless publication is separately authorized.

Evidence: `docs/releases/0.1.15.md`.

### `0.2.0` acceptance criteria

- [x] One maintained inventory classifies every model carrying a tenant foreign key as forced-RLS domain data, authorization control-plane state, or the installation singleton. Adding an unclassified tenant-bearing model fails certification.
- [x] Every tenant-owned model except the reviewed installation singleton exposes the fail-closed scoped manager, and the forced-RLS inventory exactly matches the domain-data portion of the certification contract.
- [x] PostgreSQL makes tenant membership identity and invitation ownership immutable, requires invitation actors and authorization-record creators to belong to the same tenant, and retains existing role, collection, assignment, entity, audience, and audit constraints. Runtime startup verifies the required guard inventory.
- [x] The permission and built-in-role catalogs are complete, unique, bounded, and deny custom-role access to ownership, role administration, and secret reveal. Every unsafe method on every cataloged route denies Read-only members and requires MFA where cataloged.
- [x] The accounts control-plane migration reverses and reapplies without losing membership, scoped-role, entity, archive, or audit state. Raw runtime-role RLS, route/IDOR, CSRF, cross-tenant, sibling-client, assigned-only, recycle-bin, and append-only audit suites remain blocking.
- [x] `make test-certification` is a dedicated PostgreSQL gate and is part of `make release-gate`. Version, architecture, threat model, security baseline, risk register, migration runbook, and release evidence agree at `0.2.0`.
- [x] The certified product remains one MSP per installation. Authentication-provider and authorization control-plane reads intentionally remain outside RLS because they establish tenant identity; hosted multi-MSP deployment requires a separately reviewed identity/control-plane boundary and is not claimed by this release.

ADR 0018 defines the certification inventory, control-plane integrity guards, and the accepted single-installation boundary.

Evidence: `docs/releases/0.2.0.md`.

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
| `0.2.1` | **Complete:** final Markdown dialect, semantic highlight/callouts, accessible visual/raw/preview/help modes, server allowlist rendering, malicious corpus, editor round-trip fixture gate, and resolution of `TD-RISK-014`. |
| `0.2.2` | **Complete:** workspace-aware title-first Documentation indexes, MSP/client document ownership scopes, permission-aware cross-listing references, stable blocks, ordered placements, and persistence. Live titles open the authorized editor while future STATIC publication titles open immutable output. |
| `0.2.3` | **Complete:** immutable block revisions, SHA-256 checksums, parent chains, optimistic concurrency, permission-aware history, and line diffs. |
| `0.2.4` | **Complete:** live/pinned placement resolution, cycle prevention, and deterministic transclusion. |
| `0.2.5` | **Complete:** backlinks, reuse-impact preview across client listings, permission-aware shared editing, detach, and entity mentions. |
| `0.2.6` | **Complete:** document categories, reusable templates, managed private attachments, and deterministic Markdown import/export. |
| `0.2.7` | **Complete:** immutable STATIC dependency resolution, canonical snapshot/manifest, content digest, and Ed25519 signing. |
| `0.2.8` | **Complete:** deterministic PDF artifacts, supersession/correction workflow, retention, and publication security corpus. |
| `0.2.9` | **Complete:** documentation-alpha stabilization, enforced editor/shell bundle budgets, paginated large history, accessibility, prior-alpha upgrade, and database/media restore evidence. |
| `0.3.0` | **Complete:** formally certified reusable Markdown documentation and immutable STATIC publication without expanding the domain surface. |

### `0.2.1` acceptance criteria

- [x] ADR 0019 freezes a portable technical-documentation dialect with no raw HTML, MDX, scripts, inline styles, author CSS, or arbitrary colors.
- [x] The visual editor exposes accessible structural and inline controls, semantic `==highlight==`, five typed callouts, raw Markdown, secure preview, and internally hosted formatting help without making editor HTML/JSON canonical.
- [x] The supplied UniFi guide and every supported extension pass an executable Milkdown-to-Markdown semantic round-trip fixture.
- [x] Authenticated preview uses the central `documents.view` policy, normal CSRF/session protection, a bounded request, raw-HTML-disabled parsing, an explicit server allowlist, and a second browser sanitizer.
- [x] A malicious corpus proves authored elements, event attributes, styles, and unsafe active URL schemes cannot enter rendered DOM.
- [x] The future documentation ownership model is explicit: the public repository's actual GitHub Wiki is the end-user/operator home, repository docs remain engineering artifacts, and authenticated pages may later expose concise contextual help plus stable Wiki links without executing remote content.
- [x] `TD-RISK-014` is resolved by reviewing and including the previously isolated editor/example work; `TD-RISK-013` and `TD-RISK-019` retain later owners.
- [x] Version, OpenAPI, static, unit, Docker/PostgreSQL, browser-matrix, accessibility, clean-install, upgrade, dependency, static-analysis, secret-scanning, and container evidence agree at `0.2.1`.

Evidence: `docs/releases/0.2.1.md`.

### `0.2.2` acceptance criteria

- [x] `Document`, `Block`, and ordered `DocumentPlacement` records have stable UUID identity, explicit tenant/workspace ownership, canonical Markdown content, normal migrations, and database scope guards.
- [x] MSP and organization Documentation pages list active records title-first; titles open the real authorized editor, which creates, renames, edits, and archives persisted records through Django.
- [x] An MSP-owned document can be explicitly projected into any authorized client Documentation listing without copying its document, block, Markdown, or ownership; the client listing labels that provenance.
- [x] Cross-listing does not grant mutation authority. Organization users can read only exact-workspace documents and authorized MSP references, while sibling and cross-tenant identifiers remain non-disclosing.
- [x] Every document endpoint uses the central policy service and permission inventory, and PostgreSQL forced RLS covers documents, blocks, placements, listing references, and their stable entity labels.
- [x] Runtime-role and API negative tests cover scope mismatch, sibling isolation, reference projection, and MSP ownership; the migration-cycle test removes and reapplies the new schema and policies without weakening prior RLS.
- [x] A disposable Chromium journey creates and edits an organization document, creates an MSP document, lists it in the client, verifies the client projection, and confirms the same records in PostgreSQL.
- [x] Immutable revisions, live/pinned resolution, backlinks, detach, entity mentions, attachments, and STATIC publications remain explicitly deferred to `0.2.3`–`0.2.8`.

Evidence: `docs/releases/0.2.2.md`.

### `0.2.3` acceptance criteria

- [x] Canonical Markdown is stored in immutable `BlockRevision` rows with stable UUIDs, sequential numbers, parent links, server-computed SHA-256 checksums, authors, and timestamps; existing mutable block Markdown migrates without losing document or block identity.
- [x] Every content edit locks the document and block, requires the exact base revision, and atomically appends a new revision plus advances the current pointer. Title-only or unchanged-content saves do not create redundant revisions.
- [x] A stale edit returns a structured `409 revision_conflict` with the authorized current revision and a unified base-to-current diff while leaving both the stored content and the browser's unsaved draft unchanged.
- [x] MSP and organization document routes expose permission-aware revision lists and individual parent diffs. MSP references inherit only the document's existing read projection; sibling and cross-tenant revision identifiers remain non-disclosing.
- [x] Django rejects revision instance mutation, PostgreSQL rejects raw update/delete and invalid parent/scope/current-pointer edges, and forced RLS includes revision rows under the fixed runtime role.
- [x] The Documentation interface displays current revision save feedback, accessible history loading/empty/error states, author/time/checksum metadata, selected line diffs, and an explicit conflict state without rendering revision content as HTML.
- [x] Migration-cycle, route inventory/IDOR, runtime RLS, backend/frontend, OpenAPI, Docker Compose, browser, security, clean-install, and upgrade evidence agree at `0.2.3`.

Evidence: `docs/releases/0.2.3.md`.

### `0.2.4` acceptance criteria

- [x] Every placement explicitly resolves either its block's current revision (`live`) or one exact immutable revision (`pinned`), and the primary editable block remains live.
- [x] Documents expose primary canonical Markdown, deterministic assembled Markdown, and an ordered placement/revision manifest without embedding proprietary transclusion tokens in authored Markdown.
- [x] Nested placements resolve depth first by stable sibling order under explicit 500-placement and 32-level limits; self-transclusion, ancestor block cycles, unreachable placement graphs, and invalid pins fail closed.
- [x] Placement create/update/remove routes use the central `documents.edit` policy, normal CSRF/MFA rules, destination-derived scope, non-disclosing source lookup, and route/IDOR inventory coverage.
- [x] Client compositions may use an MSP primary block only through an active client listing reference. Sibling-client sources are denied, and application plus PostgreSQL guards prevent removing a reference while a dependent client placement remains.
- [x] PostgreSQL validates placement/document/block/parent/pinned-revision scope and rejects raw cross-client placement and recursive-cycle attempts; migration and runtime-RLS evidence retain the existing isolation boundary.
- [x] The Documentation interface lists resolved blocks, revision/checksum state, live/pinned controls, removal, visible-source selection, assembled Markdown, responsive behavior, and accessible labels without making browser controls authoritative.
- [x] OpenAPI, backend/frontend, Docker Compose, browser matrix, real PostgreSQL journey, security, clean-install, upgrade, and production-image evidence agree at `0.2.4`.

Evidence: `docs/releases/0.2.4.md` after certification.

### `0.2.5` acceptance criteria

- [x] Every block exposes permission-filtered backlinks and a bounded reuse-impact projection that distinguishes source, live, pinned, and client-listing audiences without disclosing hidden clients or documents.
- [x] Editing a shared block authorizes against the block owner's MSP or organization scope, requires the exact base revision, appends through the immutable revision service, and returns the existing structured stale-write conflict.
- [x] A user who may edit the containing document but not its shared source can atomically detach a non-primary placement into a new destination-owned block at the currently resolved revision; subsequent source edits do not change the detached copy.
- [x] Detach preserves placement identity, order, and descendants while PostgreSQL scope guards validate the replacement block. Primary blocks cannot detach through the placement workflow.
- [x] Entity mentions serialize only as stable `tekdocs://entity/{uuid}` Markdown links. Mention search is workspace- and permission-scoped, and preview replaces authored labels with server-authorized reference cards or one non-disclosing unavailable state.
- [x] Shared-edit, detach, backlink, impact, and mention endpoints use the central policy service, normal CSRF/MFA rules, route inventory, and allow/deny/sibling/cross-tenant IDOR coverage.
- [x] The Documentation interface exposes reuse review before a shared save, clearly distinguishes live and pinned effects, offers detach when canonical editing is unavailable, and inserts entity references without making editor HTML authoritative.
- [x] OpenAPI, backend/frontend, Docker Compose, browser matrix, real PostgreSQL journey, security, clean-install, upgrade, and production-image evidence agree at `0.2.5`.

Evidence: `docs/releases/0.2.5.md`.

### `0.2.6` acceptance criteria

- [x] Documents carry one portable built-in category (`general`, `policy`, `procedure`, `guide`, or `reference`) and an explicit template designation; indexes can search and filter both without weakening workspace visibility.
- [x] An authorized visible template creates a new independent destination-owned document from its resolved Markdown. Source-owned managed attachments are copied under new identities and their stable Markdown references are rewritten; unsupported external attachment references fail closed.
- [x] Managed attachments have stable UUID identity, exact tenant/workspace/document ownership, randomized storage names, server-derived size/checksum/media type, bounded uploads, soft removal, and no public `/media/` serving path.
- [x] Attachment download authorizes through the owning document and returns a forced-download, `nosniff`, private response. Hidden, sibling, cross-tenant, archived, malformed, oversized, empty, and disallowed active-content cases are non-disclosing or rejected.
- [x] Attachment links serialize only as `tekdocs://attachment/{uuid}`. Preview replaces authored labels with server-authorized attachment cards or one unavailable state; attachment HTML and client-supplied media types are never trusted.
- [x] UTF-8 `.md` import creates one normal document through the existing immutable revision service under a 1 MiB limit. Export returns deterministic resolved Markdown with a sanitized filename, without secrets, private attachment bytes, or browser-rendered HTML.
- [x] Category/template/attachment/import/export routes use the central policy service, CSRF/MFA rules, route inventory, PostgreSQL guards/RLS, audit events, and allow/deny/sibling/cross-tenant IDOR coverage.
- [x] The Documentation interface adds restrained category/filter/template/import/export/attachment workflows with keyboard, responsive, loading, empty, error, and accessibility states while Markdown remains canonical.
- [x] Migration, OpenAPI, backend/frontend, Docker Compose, browser matrix, real PostgreSQL journey, security, clean-install, upgrade, and production-image evidence agree at `0.2.6`.

Evidence: `docs/releases/0.2.6.md`.

### `0.2.7` acceptance criteria

- [x] Publishing creates a separate immutable `DocumentPublication`; it never freezes or mutates the source document, and later source, block, entity, or attachment changes cannot alter retained publication content.
- [x] Publication resolves the exact ordered block revisions, authorized entity projections, and active source-document attachment metadata referenced by canonical Markdown; unavailable or foreign dependencies fail atomically and non-disclosingly.
- [x] The canonical manifest uses a versioned deterministic JSON contract containing publication/document/workspace identity, title/category, exact placement revisions, entity projections, attachment metadata, publisher, and publication timestamp.
- [x] TekDocs stores canonical Markdown, sanitized self-contained HTML, the manifest, and a SHA-256 digest of an unambiguous canonical snapshot payload; recalculation detects any stored-content or manifest change.
- [x] A maintained Ed25519 implementation signs the content digest with a deployment-supplied private key. The publication retains the algorithm, signature, public verification key, and key fingerprint, and exposes a verification result without returning private key material.
- [x] Publication rows are append-only in Django and PostgreSQL. Update/delete attempts, cross-scope edges, malformed manifests, and duplicate publication identities fail below the view layer, while source records retain normal editing.
- [x] List, detail, publish, Markdown-download, and manifest-download routes use the central `documents.view`/`documents.publish` policies, MFA/CSRF rules, forced private downloads, route inventory, forced RLS, and sibling/cross-tenant IDOR coverage.
- [x] The Documentation interface clearly distinguishes editable source documents from retained STATIC publications and provides restrained publish, list, open, verification, and artifact-download states with keyboard, responsive, denial, and accessibility coverage.
- [x] Migration, OpenAPI, backend/frontend, Docker Compose, browser matrix, real PostgreSQL journey, security, clean-install, upgrade, and production-image evidence agree at `0.2.7`.

Evidence: `docs/releases/0.2.7.md`.

### `0.2.8` acceptance criteria

- [x] Every new STATIC publication retains one generated PDF plus independent copies of every referenced managed attachment under opaque storage names; artifact identifiers, media types, byte sizes, and SHA-256 checksums are included in the signed manifest.
- [x] PDF output is deterministic for the same frozen publication inputs, uses only server-controlled presentation, carries publication identity and page numbering, and passes structural, text-extraction, and rendered-page checks without loading remote resources.
- [x] Publication requests require a bounded reason, an explicit `msp_internal` or `client_visible` audience, and a retention class. Client-visible intent is valid only for organization-owned publications and does not itself grant portal access.
- [x] Retention is either permanent or review-on-date. Reaching a review date produces a visible `review_due` state but never deletes, hides, or mutates publication evidence; TekDocs exposes no application retention purge.
- [x] A correction creates a complete new publication that references exactly one prior publication of the same source document and workspace. The prior record remains readable, the chain is acyclic and single-successor, and current/superseded state is derived without updating either publication.
- [x] PDF and retained-attachment downloads authorize through the source publication, use forced private `nosniff` responses, and reject malformed, sibling-client, cross-tenant, mismatched-source, or unretained artifact identifiers without disclosure.
- [x] Publication, artifact, supersession, audience, retention, signature, and file-failure paths are append-only and fail closed in Django and PostgreSQL; partially written storage is cleaned when publication fails.
- [x] The Documentation interface collects publication metadata before confirmation, distinguishes current and superseded STATIC records, shows audience/reason/retention state, and offers authorized PDF and retained-artifact downloads with responsive and accessible denial/error states.
- [x] Migration, OpenAPI, backend/frontend, PDF rendering, Docker Compose, browser matrix, real PostgreSQL journey, security, clean-install, upgrade, and production-image evidence agree at `0.2.8`.

Evidence: `docs/releases/0.2.8.md`.

### `0.2.9` acceptance criteria

- [x] Revision history is fully countable and navigable through validated 50-row pages with a 100-row server maximum; no fixed truncation silently hides retained revisions.
- [x] The PostgreSQL reference fixture includes 2,500 immutable revisions and proves authorized history pages remain below the 500 ms p95 target with a fixed query ceiling.
- [x] Documentation history, diffs, editor modes, and Markdown help retain keyboard, responsive, focus, live-status, and automated WCAG checks.
- [x] The editor remains route-lazy; its styles and optional syntax assets do not enter the initial shell, and executable build budgets cap the shell at 500 KiB and the current editor at 1,200 KiB minified.
- [x] ADR 0019, the fixed round-trip corpus, sanitizer/renderer tests, and internally hosted Formatting help agree. GitHub Wiki publication remains explicitly deferred until external publication is authorized.
- [x] A dedicated `0.2.8` to `0.2.9` rehearsal preserves document/block/publication identities, revision history, managed attachment bytes, signed manifest verification, and retained PDF bytes.
- [x] An isolated backup/restore rehearsal captures PostgreSQL and the media volume independently, restores both into clean volumes with deployment keys retained separately, and verifies canonical revisions, attachments, signatures, and PDF artifacts.
- [x] The backup rehearsal is evidence, not supported encrypted backup tooling; destructive safeguards, encryption, scheduling, remote storage, and key-loss recovery remain owned by `TD-RISK-006` in `0.8.1`/`0.9.3`.
- [x] Version, migration/OpenAPI drift, backend/frontend, Docker Compose, browser matrix, security, clean-install, production-image, upgrade, and documentation-specific recovery evidence agree at `0.2.9`.

Evidence: `docs/releases/0.2.9.md`.

### `0.3.0` acceptance criteria

- [x] The release adds no document model, migration, route, dependency, Markdown extension, editor behavior, or publication format; it certifies the implemented `0.2.x` contract rather than broadening it.
- [x] `make test-documentation-certification` runs the complete document/publication service and API suite with rendering abuse, authenticated-route/IDOR, raw runtime-role forced-RLS, migration-aware reference performance, and 2,500-revision history evidence against PostgreSQL.
- [x] Every document mutation remains centrally authorized and MFA/CSRF protected; every direct identifier remains non-disclosing across anonymous, non-member, Read-only, sibling-client, assigned-only, malformed, and cross-tenant cases.
- [x] Canonical Markdown, immutable revisions, live/pinned resolution, reuse impact, detach, entity mentions, templates, managed attachments, import/export, and server/client sanitization remain aligned with ADRs 0019 and 0021–0024.
- [x] STATIC publication continues to freeze exact dependency revisions and retained bytes into append-only signed manifests, deterministic PDFs, lifecycle metadata, and one-successor correction chains under ADRs 0025–0026.
- [x] Documentation-specific `0.2.8` upgrade and isolated PostgreSQL-plus-media restore rehearsals preserve identities, revision history, exact attachment bytes, signed manifests, and retained PDFs with deployment keys held separately.
- [x] The shell/editor bundle budgets, 2,500-revision latency/query ceilings, keyboard and axe behavior, and the Chromium/Firefox/WebKit matrix remain blocking without claiming the later 250,000-revision or representative-device capacity target.
- [x] Version, migration/OpenAPI drift, backend/frontend coverage, Docker Compose, production images, clean installation, oldest-supported upgrade, documentation upgrade/restore, security scans, architecture, threat model, security baseline, risk register, and release evidence agree at `0.3.0`.
- [x] Hosted GitHub checks, tags, images, attestations, Wiki publication, and deployment remain explicitly unverified and unperformed until separately authorized.

Evidence: `docs/releases/0.3.0.md`.

## Credentials and inventory: `0.3.x` → `0.4.0`

| Release | Slice and exit condition |
| --- | --- |
| `0.3.1` | **Complete:** provider-neutral credential references, strict 1Password Private Link validation, scoped RBAC, value-free audit, and explicit rejection of share links, arbitrary URLs, and secret values. |
| `0.3.2` | **Complete:** production runtime `*_FILE` inputs, fail-closed secret-file validation, service-scoped Compose mounts, production-image leakage tests, removable bootstrap custody, and an operator-owned 1Password CLI injection recipe. |
| `0.3.3` | **Complete:** supplier-workspace product/model catalogs, hardware/software template identity, and versioned specification definitions. |
| `0.3.4` | **Complete:** supplier-owned product documentation, client asset instantiation with retained product/specification/document provenance, and relationship-derived client vendor lists. |
| `0.3.5` | **Complete:** client hardware serials/tags, acquisition/disposal, warranty, current person/location assignment, and append-only lifecycle history. |
| `0.3.6` | **Complete:** client software installations, addressable licenses, bounded seat allocation, renewal terms, installation relationships, and append-only license history. |
| `0.3.7` | **Complete:** client commercial contracts, provider and renewal lifecycle, fixed-precision cost lines, exact-scope field projection, and non-disclosing list/search behavior. |
| `0.3.8` | **Complete:** MSP-owned operational parity for assets, hardware lifecycle, software installations/licenses, contracts/costs, and derived vendors without aggregating client records. |
| `0.3.9` | **Complete:** explicit immutable MSP/organization Workspace identities, non-null Entity ownership, data backfill, workspace-bound RLS input, and non-orphaning organization retention. |
| `0.3.10` | **Complete:** attachment-provider/scanner quarantine boundary, hostile-file corpus, exact-workspace asset relationships, and atomic bounded bulk operations. |
| `0.3.11` | **Complete:** canonical asset CSV import/export, signed dry-run review, bounded validation, deterministic retry identity, atomic apply, and secret-safe exclusions. |
| `0.3.12` | **Complete:** inventory/credential-reference stabilization, workspace/reference-data performance, restore, upgrade, and accessibility evidence. |
| `0.4.0` | **Complete:** formal certification of external credential references and hardware/software inventory without adding another domain family. |

### `0.3.1` acceptance criteria

- [x] Credential records contain only a scoped entity title, provider identifier, provider-owned Private Link, lifecycle timestamps, and workspace ownership; no username, password, token, note, retrieval configuration, or revealed value is accepted.
- [x] A provider-neutral adapter boundary supplies the first strict 1Password implementation. It accepts only the canonical `https://start.1password.com/open/i` Copy Private Link shape and rejects share links, arbitrary hosts/schemes, fragments, duplicate/extra/malformed parameters, invalid provider identifiers, and modified link serialization.
- [x] List and search responses omit the Private Link, search only titles, and return no secret-shaped fields. Opening uses a centrally authorized, audited same-origin handoff that revalidates the stored target before redirecting to 1Password.
- [x] Independent view, manage, and open permissions compose through built-in and custom roles at tenant, organization, and collection scope. Read-only/document permissions do not imply credential-reference access; client reachability and exact workspace scope remain hard constraints.
- [x] Create, update, archive, and open events carry the reference entity identifier but empty metadata. TekDocs does not call 1Password APIs, retrieve values, proxy provider content, or infer that possession of a reference grants provider access.
- [x] The credential-reference model has scoped managers, same-tenant/entity database guards, forced PostgreSQL RLS, negative sibling-client/MSP/tenant IDOR coverage, migration inventory coverage, and browser/component accessibility states.
- [x] Security baseline, threat model, custody ADR, information architecture, risk register, OpenAPI, release notes, and version metadata agree that customer secrets remain outside TekDocs.

Evidence: `docs/releases/0.3.1.md`.

### `0.3.2` acceptance criteria

- [x] One configuration reader supports mutually exclusive direct or `*_FILE` sources for Django signing, owner/runtime PostgreSQL credentials, MFA wrapping, STATIC publication signing, first-owner bootstrap, SMTP authentication, and OIDC client authentication without printing a value or host source path.
- [x] File inputs must resolve inside an approved root, identify a bounded regular UTF-8 file, have an expected owner and non-writable/non-executable group/other mode, and contain one printable value. Empty, oversized, multiline, outer-whitespace, non-UTF-8, relative, escaping-symlink, outside-root, unsafe-mode, missing, and ambiguous inputs fail closed.
- [x] The production Compose overlays mount only the secrets each database/migration/runtime/auth service requires beneath `/run/secrets`; the ordinary production environment example contains no secret value. Direct environment fallback remains available for development and compatibility until production enforcement in `0.8.7`.
- [x] The bootstrap secret is a separate one-time overlay. Readiness fails when an unclaimed installation has no token and succeeds after an owner claim when the token mount is removed.
- [x] The production-target rehearsal uses file-only values and verifies successful database migration plus web/worker/scheduler startup, non-root runtime, absent development tools, least-scope mounts, and no secret values in container environments, image history, or service logs.
- [x] Ambiguous direct-plus-file production startup is rejected with a value/path-free diagnostic. Local unit and Compose gates cover precedence, validation, conditional bootstrap, SMTP/OIDC resolution, and runtime-image behavior.
- [x] The operator-owned 1Password recipe materializes deployment files outside the repository on a protected host runtime filesystem. TekDocs containers receive only mounted files and never receive a 1Password account session, service-account token, Connect token, vault reference, or retrieval capability.
- [x] Security baseline, threat model, risk register, operator documentation, release notes, version metadata, and release gates agree at `0.3.2`; no schema or product API change is introduced.

Evidence: `docs/releases/0.3.2.md`.

### `0.3.3` acceptance criteria

- [x] Only active vendor- or manufacturer-classified organization workspaces may own catalog data; client-only and partner-only direct routes fail closed, while multi-classified suppliers retain one organization identity.
- [x] A supplier may create, search, open, edit, and archive stable addressable hardware or software products and concrete addressable models without accepting tenant or organization ownership from the browser.
- [x] Stable specification definitions have immutable sequential versions containing a bounded, server-validated Draft 2020-12 object schema and a server-calculated SHA-256 checksum; publishing a new version never rewrites or reinterprets prior model data.
- [x] Every model create or edit appends an immutable sequential revision pinned to one exact specification-definition version. Values validate against that schema, history remains readable, and stale base revisions return `409` without overwriting either writer.
- [x] Product/model/definition/revision relationships enforce exact tenant and supplier scope in Django and PostgreSQL; forced RLS, scoped managers, route inventory, and allow/deny/sibling/cross-tenant IDOR tests cover every route.
- [x] Catalog reads use `assets.view`; catalog mutations use the centrally declared MFA/CSRF-protected `assets.edit` permission. Supplier classification narrows access and never grants it.
- [x] The supplier Products page provides restrained search, hardware/software filtering, product/model creation, structured specification-definition versioning, model history, loading/empty/error/denial, responsive, keyboard, and accessibility states.
- [x] OpenAPI, architecture, security baseline, threat model, risk register, migration/upgrade evidence, backend/frontend tests, Docker Compose, and one non-mocked browser-to-Django-to-PostgreSQL supplier catalog journey agree at `0.3.3`.

Evidence: `docs/releases/0.3.3.md`.

### `0.3.4` acceptance criteria

- [x] Supplier product documentation associates a product and optional model with one exact immutable `client_visible` STATIC publication owned by the same supplier; live documents, MSP-internal publications, sibling-supplier records, and browser-supplied ownership fail closed.
- [x] A client asset is a new client-owned Entity created from one active supplier model. The server derives and retains the exact supplier, product, model, current model revision, specification-definition version, validated specification values, and server-calculated provenance checksum.
- [x] Asset creation captures every applicable active product-level and model-level publication association as immutable document-provenance rows. Later model revisions, specification versions, publication corrections, association archival, or label changes do not rewrite an existing asset.
- [x] Client asset reads expose the retained supplier/model/specification/publication identities and verified STATIC document projections without granting access to the supplier workspace or accepting a generic cross-organization document identifier.
- [x] The client Vendors page is derived from active client asset provenance, returns each supplier once with an asset count, and does not create a second vendor record, mutable label match, or implicit EntityLink.
- [x] Catalog-document association uses `documents.view` plus MFA/CSRF-protected `assets.edit`; client asset/model discovery and reads use `assets.view`, while creation uses MFA/CSRF-protected `assets.edit`. Every decision remains in the central policy service.
- [x] Product-document, client-asset, and asset-document relationships enforce same-tenant and exact supplier/client scope through Django validation, PostgreSQL guards, scoped managers, forced RLS, append-only provenance triggers, and allow/deny/sibling/cross-tenant IDOR coverage.
- [x] Supplier Products, client Assets, and client Vendors provide restrained loading, empty, error, denial, responsive, keyboard, and accessibility states; one non-mocked browser journey proves supplier publication association through client asset creation and retained database provenance.
- [x] OpenAPI, architecture, security baseline, threat model, `TD-RISK-022`, migration/upgrade evidence, tests, Compose runtime, roadmap, release notes, and version metadata agree at `0.3.4`; serials, acquisition/disposal, warranty, assignment, costs, and mutable asset lifecycle remain later slices.

Evidence: `docs/releases/0.3.4.md` (created at slice closeout).

### `0.3.5` acceptance criteria

- [x] Every client asset backed by a hardware catalog product has one client-scoped hardware profile; software assets fail closed at every lifecycle route and remain owned by `0.3.6`.
- [x] Serial numbers and asset tags are optional, normalized identifiers that are unique within one client organization when present. Acquisition method/date/reference and warranty provider/start/end/reference are bounded, validated fields; costs and contracts remain deferred to `0.3.7`.
- [x] Hardware follows an explicit in-stock, in-service, repair, retired, or disposed lifecycle. Disposal records method/date/reason, clears current assignment, and is terminal through ordinary application workflows.
- [x] Current assignment may identify an active person association and/or structured site/location from the exact client organization. Reassignment and unassignment preserve history; sibling-client and cross-tenant targets fail without disclosure.
- [x] Creation, material detail changes, assignment changes, state changes, and disposal update current state and append an immutable lifecycle event in one locked transaction. Events are protected against application and direct PostgreSQL update/delete.
- [x] Hardware profile, assignment, and lifecycle relationships enforce tenant/client scope through model validation, PostgreSQL guards, scoped managers, forced RLS, and allow/deny/sibling/cross-tenant IDOR coverage.
- [x] Reads use `assets.view`; every mutation uses centrally declared MFA/CSRF-protected `assets.edit`. Audit events contain identifiers and action names but no serial, acquisition reference, warranty reference, assignment note, or disposal reason.
- [x] The client Assets experience exposes restrained hardware identity, acquisition, warranty, assignment, lifecycle, loading, empty, error, denial, responsive, keyboard, and accessibility states; one non-mocked browser-to-Django-to-PostgreSQL journey proves retained history.
- [x] OpenAPI, architecture, security baseline, threat model, risk register, migration/upgrade evidence, tests, Compose runtime, roadmap, release notes, and version metadata agree at `0.3.5`.

Evidence: `docs/releases/0.3.5.md`.

### `0.3.6` acceptance criteria

- [x] Every client asset backed by a software catalog product receives one client-scoped installation profile; hardware assets fail closed at software routes.
- [x] Installation state records planned, installed, suspended, or terminal uninstalled status plus bounded version, installation date, verification date, and optional exact-client site.
- [x] An addressable client license retains its supplier software product/model relationship, subscription/perpetual/trial kind, status, seat limit, term, renewal date/interval, auto-renew choice, and bounded external reference without storing license keys or credentials.
- [x] One license may cover multiple exact-client installations of the same retained product. Active seat allocations may target a person, a linked installation, or both; allocation rejects exhausted limits, duplicate active targets, sibling-client targets, and inactive licenses.
- [x] License changes, installation relationships, assignments, and revocations append value-minimized immutable events. Audit metadata contains no renewal reference or assignment value.
- [x] Reads use `assets.view`; every mutation uses centrally declared MFA/CSRF-protected `assets.edit`. Tenant/client scope is enforced through scoped queries, PostgreSQL relationship guards, forced RLS, and negative IDOR coverage.
- [x] Client Assets exposes software installation state and Client Licenses exposes entitlement, seats, installations, renewals, history, loading, empty, denial, responsive, keyboard, and accessibility states.
- [x] OpenAPI, architecture, security baseline, threat model, risk register, migrations, tests, Compose runtime, roadmap, release notes, and version metadata agree at `0.3.6`.

Evidence: `docs/releases/0.3.6.md`.

### `0.3.7` acceptance criteria

- [x] A client may create, search, open, edit, and archive an addressable commercial contract related to one eligible same-tenant vendor, manufacturer, or partner provider.
- [x] Contract kind, lifecycle, description/reference, term, renewal date, auto-renew choice, and notice period remain operational fields readable through `assets.view`; mutations use MFA/CSRF-protected `assets.edit`.
- [x] Fixed-precision cost lines support a bounded label, non-negative amount, normalized three-letter currency, positive quantity, billing interval, term, and reference without using floating-point storage.
- [x] Every cost field is one centrally classified projection. Without exact-scope `costs.view`, the `costs` member is absent rather than null, masked, summarized, or counted; cost mutation additionally requires `assets.edit`.
- [x] Contract list/search considers only non-cost contract and provider fields. Amounts, currency, quantities, cost labels/references, totals, ordering, highlighting, and result counts cannot act as a cost oracle.
- [x] Contract/entity/provider/cost relationships enforce exact tenant/client scope through model validation, PostgreSQL guards, scoped managers, forced RLS, and allow/deny/sibling/cross-tenant IDOR tests.
- [x] Audit events are value-free, and the Services UI exposes contracts, providers, terms, renewals, explicit hidden-cost guidance, loading/empty/error/denial, responsive, keyboard, and accessibility states.
- [x] OpenAPI, architecture, security baseline, threat model, risk register, migrations, tests, Compose runtime, roadmap, release notes, and version metadata agree at `0.3.7`.

Evidence: `docs/releases/0.3.7.md`.

### `0.3.8` acceptance criteria

- [x] The MSP is an operational owner represented by its explicit Workspace (introduced in `0.3.9`); its `organization IS NULL` projection never represents a synthetic client or an aggregate query over client-owned records.
- [x] MSP routes expose the existing asset, retained catalog/document provenance, hardware lifecycle, software installation/license, seat, contract/cost, and derived-vendor workflows through the same domain services used by client workspaces.
- [x] Every operational row and related Entity carries one exact owner scope. Nullable PostgreSQL relationship guards use null-safe comparison, MSP serial/tag uniqueness remains database enforced, and forced RLS denies missing or mismatched scope.
- [x] MSP catalog access is a narrow read-only projection of supplier catalogs and associated client-visible STATIC publications; it does not make client assets, client documents, licenses, contracts, people, sites, or costs visible in MSP scope.
- [x] The central route inventory covers every new MSP endpoint. Negative tests prove MSP lists exclude client records, client lists exclude MSP records, and direct identifiers cannot cross either boundary.
- [x] MSP navigation renders Assets, Licenses, Services, and Vendors as real surfaces with workspace-aware wording, loading, empty, error, responsive, keyboard, and accessibility behavior.
- [x] OpenAPI, architecture, information architecture, security/threat model, `TD-RISK-026`, migrations, tests, Compose runtime, roadmap, release notes, and version metadata agree at `0.3.8`.

Evidence: `docs/releases/0.3.8.md`.

### `0.3.9` acceptance criteria

- [x] Each installation tenant has exactly one immutable MSP Workspace and every organization has exactly one immutable organization Workspace; this does not change the supported one-MSP-per-install topology.
- [x] Every universal Entity has a non-null Workspace owner. The migration backfills existing MSP and organization records before enforcing the constraint.
- [x] Entity creation resolves ownership explicitly and ordinary creation without a Workspace fails closed instead of silently treating a missing organization as MSP ownership.
- [x] Django validation and PostgreSQL guards require exact tenant/workspace/organization agreement and reject Workspace identity mutation or deletion.
- [x] Organization archival retains its organization, Entity, Workspace, and all child ownership links. Protected relationships prevent physical organization deletion and orphaned data.
- [x] Transaction-local RLS scope includes the internal Workspace UUID; Entity writes require the bound owner while approved permission-aware document/catalog projections remain read-only.
- [x] The ownership control-plane classification, runtime startup guard inventory, negative isolation tests, migration drift, architecture, threat model, security baseline, risk register, release notes, and version metadata agree at `0.3.9`.

Evidence: `docs/releases/0.3.9.md`.

### `0.3.10` acceptance criteria

- [x] Attachment storage and scanning use replaceable interfaces; opaque quarantine precedes checksum-verified promotion, and failed intake leaves no managed record or downloadable bytes.
- [x] Only clean attachments are addressable. Records retain provider/scanner identity and scan time; download, template copy, and STATIC reads recheck stored size and SHA-256.
- [x] The built-in scanner rejects executable/polyglot signatures, the standard AV test marker, active PDFs, malformed image containers, unsafe text controls, and ZIP traversal, encryption, symlinks, nested archives, excessive entries, expansion, or compression ratio without extracting content.
- [x] Scanner/provider failure is non-disclosing and fail-closed. The built-in scanner is documented as defense in depth rather than a maintained external malware-signature engine.
- [x] Asset relationship search, links, and backlinks reuse `EntityLink`, relationship permissions/MFA, and exact MSP/client workspace visibility; sibling-client targets remain unavailable.
- [x] Bulk asset requests accept 1–100 unique IDs and lock the complete exact-workspace set before an atomic hardware-state or recoverable archive action. Invalid, foreign, mixed, disposed, or dependency-blocked input rolls back the entire request.
- [x] Hardware bulk state changes retain lifecycle/audit evidence. Archive refuses active software license relationships and enters the scoped recycle bin without losing provenance or ownership.
- [x] The Assets and Documentation surfaces expose restrained selection, scan status, relationship, bulk confirmation/error, loading, empty, responsive, keyboard, and accessibility states while treating server denial as authoritative.
- [x] Permission inventory, IDOR/RLS tests, migration/upgrade evidence, OpenAPI, architecture, security/threat model, risks, Compose, release notes, and version metadata agree at `0.3.10`.

Evidence: `docs/releases/0.3.10.md`.

### `0.3.11` acceptance criteria

- [x] TekDocs owns a versioned `tekdocs.assets.v1` exact-header contract and downloadable header-only template; arbitrary column mapping and third-party formats remain later adapters.
- [x] Export is `assets.view`-authorized and exact-Workspace scoped. Its explicit allowlist excludes assignments, disposal, licenses, costs, contracts, attachments, credential references, secrets, and internal provenance payloads.
- [x] Spreadsheet-formula-shaped exported cells are escaped, while canonical re-import restores the literal value. UTF-8 decoding, malformed structure, null bytes, file/row/cell bounds, duplicate/unknown/reordered columns, UUIDs, dates, enums, field sizes, catalog kind, and workspace identifiers validate server-side.
- [x] Import requires MFA/CSRF-protected `assets.edit`, a dry run, and a separate apply. The 15-minute signed token binds the exact bytes, Workspace UUID, and normalized action digest; changed, expired, forged, or cross-workspace previews fail closed.
- [x] New rows require a stable `import_key` that deterministically resolves one Workspace-owned Entity identity. Existing rows use `asset_id`; retry becomes an unchanged skip, while CSV cannot retarget retained supplier/model provenance.
- [x] Apply reparses under the current authorization boundary and runs the complete file in one transaction through ordinary creation/lifecycle/audit services. Invalid rows cannot commit a prefix.
- [x] The Assets surface exposes export, template guidance, file selection, create/update/skip/error counts, row review, explicit apply, loading, error, keyboard, and responsive states; server denial remains authoritative.
- [x] Backend hostile-file, duplicate-identifier, retry, formula-escape, MSP/client isolation, frontend component, OpenAPI, Compose, architecture, threat-model, risk, and release evidence agree at `0.3.11`.

Evidence: `docs/releases/0.3.11.md`.

### `0.3.12` acceptance criteria

- [x] Asset, software-license, commercial-contract, and credential-reference collections use validated bounded pagination with stable ordering, exact counts, and no unbounded serialization; reference-data choices retain explicit server caps.
- [x] Representative PostgreSQL data spans 100 client workspaces and includes supplier catalogs, hardware/software assets, lifecycle history, licenses/seats, contracts/costs, and credential references. Authorized first/middle/last-page reads retain fixed query ceilings and p95 below 500 ms without cross-workspace caches.
- [x] Concurrent seat allocation cannot exceed the retained limit, bulk/CSV retry and rollback remain atomic, archive/recovery retains exact Workspace ownership and provenance, and archived credential references cannot be listed, opened, or guessed.
- [x] Credential-reference guidance explains stale or moved provider items, replacement through a new Private Link, and the fact that TekDocs cannot validate provider access or item existence without weakening external custody. Provider links and customer values remain absent from list/search/export/audit/browser content.
- [x] Cost-denied collection pagination, counts, search, errors, CSV, and reference fixtures expose no cost member, value, total, count, ordering, or timing-dependent filter path; MSP pages remain exact-MSP views rather than client aggregates.
- [x] The inventory and credential-reference interfaces expose accessible pagination, loading, empty, denial, stale-workspace, confirmation, and keyboard/focus behavior across MSP and client contexts; one non-mocked browser journey covers the retained provider handoff and inventory navigation.
- [x] A `0.3.11` to `0.3.12` upgrade rehearsal preserves representative Workspace, catalog revision, asset provenance, lifecycle, license/seat, contract/cost, CSV retry identity, and credential-reference records. A separate database/media backup-and-restore rehearsal preserves the same database identities without treating provider links as retrievable secrets.
- [x] A dedicated inventory certification gate composes inventory, commercial, credential-reference, permission/IDOR, forced-RLS, migration, concurrency, reference-performance, and recovery suites. OpenAPI, architecture, security/threat model, risks, Compose, production images, version metadata, and release evidence agree at `0.3.12`.

Evidence: `docs/releases/0.3.12.md`.

### `0.4.0` acceptance criteria

- [x] The release adds no inventory model, migration, route, provider capability, secret-value custody, import field, or cross-client reporting surface; it certifies the implemented `0.3.x` contract rather than broadening it.
- [x] `make test-inventory-certification` runs the supplier catalog, asset/provenance, hardware/software lifecycle, licensing, commercial/cost, credential-reference, hostile-attachment, relationship, recovery, authenticated-route/IDOR, forced-RLS, migration, concurrency, and reference-performance suites against PostgreSQL.
- [x] MSP and client operational routes resolve one explicit Workspace before policy and pagination; MSP pages remain non-aggregate, client pages remain exact-organization, and cost-denied responses omit the protected member completely.
- [x] Customer credential values remain outside TekDocs. Lists, search, export, audit metadata, and browser content omit provider pointers; handoff remains separately authorized and 1Password remains responsible for item existence, vault access, unlock, reveal, and value audit.
- [x] Catalog revisions, retained document/specification provenance, hardware lifecycle, software entitlements and seats, contract costs, attachments, relationships, CSV retry identity, and credential-reference lifecycle retain their append-only, exact-Workspace, and atomicity invariants.
- [x] The `0.3.12` to `0.4.0` upgrade rehearsal and independent PostgreSQL/media restore preserve representative subsystem identities, checksums, retained bytes, lifecycle/history, protected costs, and external pointers without treating pointers as retrievable secrets.
- [x] Version, OpenAPI/migration drift, backend/frontend coverage, Docker Compose, browser matrix, real-stack journey, security scans, production image, clean installation, architecture, threat model, risk register, and release evidence agree at `0.4.0`.
- [x] “Certified” means the documented local repository gates passed for the implemented one-MSP-per-installation boundary. It is not third-party certification, a penetration-test result, provider validation, or a hosted multi-MSP claim; hosted checks, tags, images, attestations, and deployment remain unperformed without authorization.

Evidence: `docs/releases/0.4.0.md`.

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
| `0.8.8` | Operator, security, backup, upgrade, API, and end-user documentation completion; publish the end-user/operator corpus to the public repository's actual GitHub Wiki, add drift/link checks, and connect stable page-level contextual help to the relevant Wiki topics. |
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
