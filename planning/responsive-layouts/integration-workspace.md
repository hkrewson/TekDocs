# Integration workspace

## Scope

Phase 6 separates the MSP and organization Integrations routes into focused
Connections, Imports, Reconciliation, Git exports and Webhooks sections. Existing
workspace authorization, read-only provider boundaries, preview-before-apply
imports, explicit reconciliation decisions and one-time secret handling remain
authoritative.

## Acceptance

- Opening Integrations shows Connections without loading export documents or
  unrelated section data.
- Every workflow has a stable section URL that survives reload and browser history;
  desktop links become one labeled selector below 768px.
- Provider, reconciliation and export collection failures can be retried in place.
- Connection and credential drafts, selected import files and matches, export
  selections, webhook drafts and unacknowledged one-time secrets block navigation
  and support Keep editing or Discard changes.
- The connection editor remains inline so section navigation stays reachable while
  a draft is active.
- Existing connections have a focused Edit action for name, provider API URL and
  sync interval. Credentials remain a separate replacement workflow. NetBox site
  roots are normalized to the provider's `/api/` endpoint on create, edit and sync,
  including connections saved before this correction.
- Unmatched NetBox observations expose a direct **Link to TekDocs** action in
  the TekDocs-record column, beside the missing relationship instead of in a
  far-right action column. The
  matching search is explicitly identified as TekDocs-only, carries the remote
  type and ID without retyping, and permits an existing eligible record to be
  linked. NetBox racks, hardware devices, VLANs and prefixes can create and link
  their canonical TekDocs records in one transaction after the operator supplies
  the required TekDocs context;
  the drawer opens on existing-record linking and presents creation as a clear
  alternative.
- Both MSP and organization routes fit 320, 390, 768, 1024, 1280 and 1440px in
  Chromium, Firefox and WebKit without horizontal page overflow or automated
  accessibility violations.

## Evidence

- Focused workflows: `frontend/src/integrations/Integrations.test.tsx`
- Import safety: `frontend/src/integrations/Imports.test.tsx`
- Webhook and one-time-secret safety: `frontend/src/integrations/Webhooks.test.tsx`
- Responsive browser matrix: `frontend/e2e/integrations-layout.spec.ts`
- Existing shell coverage: `frontend/e2e/shell.spec.ts`
- Real organization webhook journey: `frontend/e2e/live-workspace.spec.ts`

The focused component suites pass 17 cases. The production browser run passes 84
cases across the integration matrix and existing shell suite in all three
maintained engines. The exact backend webhook, provider, stabilization and
validation targets pass with their permission, row-level isolation and migration
matrices. The isolated real-workspace journey passes against PostgreSQL in 3.4
minutes, including one-time webhook secret issuance, acknowledgement and retained
endpoint state. The repository-wide gate passes all 640 frontend tests in 117
files, the 37-page Wiki contract, API/schema and migration agreement, policy
checks, the production build and compressed bundle budgets (shell 129173 <=
131072; shell style 24503 <= 24576).

## Connection correction checkpoint — 2026-09-27

Connection editing now preserves unsaved values, keeps provider credentials
unchanged, validates provider interval and URL rules on the server, and resets a
stale provider error after an API URL correction. PostgreSQL continues to protect
tenant, workspace, organization, provider and creator identity while deliberately
allowing the API URL to change. Focused backend and frontend regression suites,
lint, types, production compilation, bundle budgets and OpenAPI agreement pass.
Version remains 0.8.46.

NetBox authentication accepts both maintained v2 tokens (`Bearer nbt_…`) and
legacy v1 tokens (`Token …`). The connection form explains that the complete v2
value is required, and credential replacement is a labeled connection action.

## NetBox first-run adoption checkpoint — 2026-09-27

The reconciliation and source-record tables no longer leave an unmatched NetBox
identity as an unexplained dead end. **Not linked** means no TekDocs identity has
been chosen; **Needs review** means an open reconciliation decision exists. The
new drawer searches eligible local records of the matching type, explains that
NetBox records themselves do not appear in that search, and creates a starting
rack when the workspace has no rack to match. Rack creation still requires a
canonical TekDocs site, so an entirely empty workspace is directed to create its
site before adopting the rack.

The API operation requires both `integrations.manage` and `networks.edit`, locks
the open exact-Workspace conflict, validates the local entity type, creates the
`NetBoxReference` with the observed fingerprint, and resolves the conflict in
one transaction. It never writes to NetBox. Direct creation for devices, VLANs,
prefixes, addresses, and MAC addresses initially remained a later extension
because those records require product, addressing, or asset dependencies that
cannot be safely guessed from the current value-minimized observation.

## NetBox prefix adoption checkpoint — 2026-09-27

An unmatched NetBox prefix can now create and link a canonical TekDocs subnet in
the review drawer. The provider boundary retains only the primitive prefix needed
for the reviewed form; nested NetBox tenant, VRF, VLAN and other provider data do
not cross into the saved observation. The form prefills the network prefix when
available and preserves explicit operator control over the TekDocs name and
description. Canonical CIDR, address-family derivation, overlap protection, audit,
reference fingerprinting and conflict resolution run through the ordinary subnet
service in one transaction. The new subnet begins in the default routing table;
optional VRF and VLAN associations can be added from its network record.

Focused backend and frontend coverage verifies the safe projection and atomic
create-and-link workflow. IP-address and MAC-address creation remain separate
dependency-aware slices. Version remains 0.8.46.

### Linking visibility correction

The original action was technically available but placed beyond the core record
state in a wide table, and unmatched racks opened with creation preselected. The
corrected layout puts **Link to TekDocs** in the visible TekDocs-record cell in
both Source records and Reconciliation. Racks now start with **Link it to an
existing TekDocs rack** selected, while **Create a TekDocs rack from this record**
remains available when no corresponding rack exists.

### Current-record collection and device adoption correction

Source records now collapse repeated sync observations by connection, remote
type, and remote identity, keeping only the latest immutable observation in the
operational collection. The retained sync jobs remain the history boundary.
Current records sort deterministically by type and remote identity, use bounded
25-row pages, and support full-collection source-name/ID search and type filtering
through URL state. This keeps NetBox devices visible before the much larger IPAM
collection and prevents each sync from multiplying apparent records.

An unmatched `dcim.device` can now create and link a TekDocs hardware asset in
one reviewed transaction. The operator must choose an existing active hardware
supplier model; TekDocs never guesses the device model from the minimized NetBox
projection. The operation requires integration, network, and asset edit access,
creates the ordinary in-stock asset and lifecycle record, then records the
NetBox identity and resolves the open conflict. Existing-asset linking remains
the default. No write is sent to NetBox. Prefixes, addresses, and MAC addresses
still require their canonical TekDocs dependencies before linking.

### VLAN adoption correction

An unmatched `ipam.vlan` can now create and link the ordinary workspace-scoped
TekDocs VLAN from the same review drawer. Existing-record linking remains the
default. Creation keeps the NetBox name as an editable starting value, requires the
operator to enter the authoritative VLAN ID from 1 through 4094, and accepts an
optional description. TekDocs does not infer the VLAN ID from a display label or
the NetBox object's unrelated remote database ID.

The backend uses the existing VLAN domain service, validates uniqueness and range,
creates the `NetBoxReference` from the exact reviewed observation, and resolves the
conflict in one transaction under integration-manage and network-edit permissions.
No write is sent to NetBox. Prefixes, addresses, and MAC addresses remain later
slices because their routing, subnet, device, or interface relationships require
separate reviewed input.

### Bounded review queue correction

Every current source-record response now includes its own open reconciliation
summary. The visible **Link to TekDocs** action therefore remains available even
when more than one page of conflicts exists; it no longer depends on a separate
mixed-status conflict request or the position of that conflict in a first-page
result.

Reconciliation now requests open items on the server before pagination and adds
URL-backed full-collection search and record-type filtering. It uses deterministic
25-row pages and keeps the count/paging state aligned after a decision. Resolved
history remains retained in the database and compatible API consumers can still
request all statuses by omitting the new status filter. Focused API coverage proves
that thirty older resolved conflicts cannot hide a later open device or rack, and
the frontend coverage verifies the open-only query, durable search URL and explicit
decision workflow.
