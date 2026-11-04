# Native template enrollment

Bounded clean-start 1.0 slice following native keys at `e6224338`.
The maintainer authorizes implementation, regression/browser/isolation/recovery
validation and direct-main commit/push after validation. Version remains 0.9.18
development. Do not deploy, migrate existing documents or change retained data.

## Acceptance

- Author an MSP template and enrolled client document entirely through supported
  Git-backed controls, without creating legacy Document/Block compatibility rows.
- Preserve the existing section semantics: independent copy, live source and fixed
  pin. The client introduction remains independently editable. Source metadata and
  template declarations are Git-owned; enrollment authorization is exact and scoped.
- Preview additions, changes and removals against the exact saved source/client
  state. Apply only reviewed updates. Refuse stale previews and preserve local
  edits/conflicts; no silent replacement or conversion of independent copies.
- Reuse existing permitted template-library boundaries. A client can access an
  explicitly approved source section, never arbitrary MSP documents/repository
  content, another client's data, legacy fragment shadows or another tenant.
- Freeze selected source text/proof in signed publications; later source edits,
  changes of pin or enrollment must not change retained publications, PDFs or
  existing primary-file versions. Missing, archived and unavailable source states
  fail closed while independent copies remain usable.
- Exercise copy/live/pinned, reviewed updates and denials through real browser
  controls. Carry new fixtures through maintained independent encrypted recovery
  and verify rollback guards. Use only the existing tekdocs Docker project locally,
  synthetic test databases within its existing database service, and hosted CI for
  separate-environment upgrade/recovery rehearsals.
- Align migration guards/RLS inventory, API/OpenAPI/types, tests, architecture,
  Wiki draft and release/roadmap status. Complete source and security review before
  the authorized push. Preserve unrelated local documentation edits.

Automatic legacy migration, monitored-source setup, interface redesign, release
version/tag publication and production operations remain outside this slice.

## Initial source findings

Existing template instantiation and enrollment resolve legacy Document records;
foreign template composition validates legacy placements and enrollment maps.
The Docker regression `test_native_template_configuration_has_no_legacy_owner_requirement`
reproduced HTTP 404 for a Git-only source at the new template-control boundary.
Existing immutable
publication, Git transaction, central policy and template review mechanisms must
be reused where their contracts fit. A new narrow native enrollment boundary is
required rather than granting broad source-Workspace access.

## Implementation contract

Saved MSP repository documents explicitly opt into the client template library.
Selected immediate native text fragments are approved source sections. A native
registry and immutable definition revisions retain source identity; each client
enrollment owns its exact Workspace, reviewed revision and ordered section map.
Copies receive destination-owned fragment IDs. Live and pinned references use the
narrow approved-library loader, never general access to the source repository.

Client introductions and copies remain independent. Update review compares both
accepted destination state and immutable source revisions. Explicit keep retains
local work; removal of a borrowed section requires an explicit conversion to local
text. Detach copies the selected bytes. Ordinary metadata editing cannot forge or
rewrite enrollment references.

Native publication evidence v4 retains the exact approved definition, selected
source bytes, Git object proof and enrollment reference. Historical evidence v1–v3
keeps its original rules. Native binding snapshots, signed PDFs and independent
primary-file history remain in the publication custody chain. Schema rollback
must refuse to discard retained native enrollment or v4 evidence.

## Validation and delivery status

Combined Docker validation passes 796 cases across authoring, discovery, existing
migration/publication families, template enrollment, rollback and route authorization.
The final full frontend suite passes 883 cases with coverage, including the new
UI/shell and explicit-label regressions; 14 safe-diagnostic cases also pass. Lint, strict types, OpenAPI,
schema drift, build/bundle limits, Bandit and the current source-secret scan pass.
All 15 real Chromium journeys and their server-side retained-state verification
pass without retries. Local gates and both source-review axes agree; exact-source
hosted validation follows the authorized direct-main push. Independent encrypted restore and supported upgrade runs require
the hosted environment; the local fixture uses only synthetic records in the
existing development database service.

Verified targeted Docker evidence includes mixed enrollment API behavior; exact
scope and permission denial; source archive, revocation, removal and offline-custody
handling; injected late-write compensation; offline v4 verification; SQL source
forgery rejection; guarded and empty rollback; recovery fingerprints; and client
delivery with/without primary files. Both independent source-review axes are clear
after correction of their reported availability and discovery findings.

Reproductions and corrections:

- Native template controls returned 404 before implementation.
- Removed sections blocked their own public review route; archiving a root or
  section did not reliably revoke availability. Exact control routes and explicit
  unavailable projections now preserve review and independent-copy workflows.
- Offline source Git blocked independent-copy reads and publication. Validated
  unavailable source custody is isolated to affected borrowed content; all-copy
  publication no longer pins an unnecessary source repository.
- Graph, ordinary list and search exposed stale foreign content when requested
  first after revocation. These boundaries now refresh authorization before using
  projections. Four discovery regressions also verify the native template filter.
- First browser setup used a tenant/entity identifier as a managed Workspace key.
  The fixture now resolves exact ownership; its Docker regression passes.
- Two complete browser runs passed 14 existing journeys but the new journey's
  exact Markdown-label lookup failed after enrollment. Runtime-role source reads,
  delayed UI and full-shell tests passed. Added safe diagnostics proved the actual
  source request returned 200 in 1.2 seconds and the editor existed. A Docker
  Chromium reproduction then showed that the wrapped label included prepopulated
  textarea text in the exact lookup. The correction explicitly associates the
  label and textarea; the original exact assertion, deadlines and zero retries
  remain unchanged. The next full replay passed that assertion and reproduced a
  separate helper ambiguity: both the save acknowledgement and repository loading
  message have status roles. The helper now selects the exact acknowledgement
  within status roles and still verifies its complete text and HTTP success.
  The next replay passed copy/live/pinned behavior, stale-review rejection,
  detach, exact-client isolation and keyboard opening, then reproduced horizontal
  overflow when resizing from desktop to the 390-pixel viewport. A full-shell
  Chromium reproduction isolated the existing animated desktop margin: immediate
  page width was 523 pixels. Disabling only that transition at the existing mobile
  breakpoint yields 390/390 immediately, preserving desktop collapse and sidebar
  animation. The original no-overflow assertion remains; full browser/accessibility
  confirmation passed on the following replay. Its final read-only check then
  reproduced a fixture authorization gap: the reader lacked assignment to the new
  assigned-only client. A restricted-role regression verifies all three read
  boundaries deny before assignment, return read-only state afterward, and keep
  writes denied. The browser fixture now assigns the reader only to that client.
  The first fixture correction imported the assignment helper from the wrong
  module; Docker test collection reproduced that error. The corrected import
  uses the existing account access-control service and passes collection.
  The final full run passes all 15 journeys and server verification, including
  exact read-only access, disabled mutation, phone layout and accessibility.
- Existing frontend tests lacked the additional native catalog transport; catalog
  controls collided with legacy labels, and cancelling a stale enrollment retained
  an obsolete catalog. Reproduced cases now preserve isolated controls and reload
  the catalog without changing the user's draft or weakening assertions.

Hosted exact-source upgrade/independent encrypted recovery remains required for
final delivery status. The combined Docker command is the
union of `test-content-authoring` and `test-document-migration-inventory`, plus the
complete permission route matrix, adapted to `docker compose exec` in the existing
project. Separate-stack upgrade/encrypted restore and production-image gates are
reserved for hosted CI under the local environment constraint; workflow syntax is
also confirmed there. No new local Compose project, service or data volume is used.

## Closeout boundary

- **Verified locally:** 796 combined backend cases, 883 frontend cases with coverage,
  14 safe-diagnostic cases, all 15 browser/server journeys, narrow follow-up runtime
  reader tests, rollback guards/empty recovery, retained signatures/PDFs/files,
  source review, static/contracts/build checks and Wiki draft/link validation.
- **Inferred:** no production readiness or deployment result is inferred from local
  synthetic tests. The new source shape remains standalone native Markdown sections;
  source-owned keys/entities/files and nested graphs need a separate contract.
- **Blocked locally by environment policy:** separate-stack supported upgrades,
  independent encrypted restore and production-image/security gates run in hosted
  CI. Workflow syntax also requires its hosted check. Exact-source results follow
  the push; no production access or existing-data transition is authorized here.

Unrelated pre-existing planning edits and ignored machine-specific instructions
are excluded from the slice commit. The Wiki change remains a local draft.
