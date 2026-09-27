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
- Unmatched NetBox observations expose a direct **Link or create** action. The
  matching search is explicitly identified as TekDocs-only, carries the remote
  type and ID without retyping, and permits an existing eligible record to be
  linked. A NetBox rack can create and link a TekDocs rack in one transaction
  after the operator selects its required TekDocs site and optional location.
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
prefixes, addresses, and MAC addresses remains a later extension because those
records require product, addressing, or asset dependencies that cannot be safely
guessed from the current value-minimized observation.
