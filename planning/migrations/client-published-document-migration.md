# Client-published document migration (#105/#106)

## Authorized slice and acceptance

Continue from `34f7b864` on main. The maintainer authorizes implementation,
validation, review, and one descriptive direct-main commit/push. Preserve client
access, signed publications, PDFs and every managed-file version. Verify portal
workflows, tenant/client isolation, rollback and independent recovery. Production
migration/deployment and Wiki publication are separate actions. Development remains
on 0.9.17 until a separately prepared runtime candidate.

Test seams already specified by the request: reviewed migration preview/import
and authority transition; publication preflight/create/approve/correct/withdraw;
client portal list/detail/download and notification targets; real staff/client
browser interactions; supported upgrade and encrypted recovery. Retained snapshot
and file reads compare original bytes and signatures, not regenerated output.

- Allow valid client-visible history alongside internal history without replacing
  identities, signatures, controls, portal links, notification targets or files.
- Preserve permanent and review-on-date retention metadata and lifecycle behavior.
- Include the maintainer-approved MSP-only and client-only section extension.
  Preserve section profiles and nesting; retain the shared primary section and
  existing reversible ownership/library boundaries.
- Pin new Git snapshots to the selected audience's verified composition. Freeze
  keys/entities/files/diagrams through existing audience authorization. Never
  substitute internal composition for client composition.
- Client snapshots remain pending until independent authorized approval. No
  migration action grants access, approves a pending record or reopens a withdrawn
  or superseded record. Existing portal routes and policy remain authoritative.
- Enforce exact Workspace/tenant/client scopes and same-audience correction chains.
  Deny private/foreign dependencies, stale plans, damaged custody and unauthorized
  writes without partial state. Retained history must remain independently readable.
- Verify real portal reads/downloads/notifications before and after promotion,
  correction, withdrawal, rollback and re-promotion. Verify file/PDF bytes, controls,
  Git sources and portal eligibility after independent restore.

Use the existing local `tekdocs` services and a generated test database in its
existing database service. Inspect Make/script topology before execution; fresh/
upgraded and independent encrypted-restore environments run in hosted CI.

General cross-Workspace reuse, product features unrelated to this migration,
production data changes and aggregate 1.0 acceptance are outside this slice.
Original unexplained notification/browser failures retain their investigation
obligations. This work accepts or renews no existing security/tooling exception.

## Evidence

Implementation, both source-review axes and local validation are complete: 623
combined Docker cases, ten final portal/edge cases, 795 frontend cases and seven
real browser/server journeys with zero retries. The [development evidence and
risk disposition](../releases/client-published-migration-notes.md) distinguish
verified checks, inference and local topology constraints. Exact-source hosted
Build, CodeQL and Extended validation are the completion authority for fresh/
0.8.46 upgrade, independent encrypted restore and production-image rehearsals.
Inspect the Actions checks and commit-bound artifacts on the feature commit
following `34f7b864`; no separate operator follow-up or release is implied.
