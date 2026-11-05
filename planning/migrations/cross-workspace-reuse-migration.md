# Remaining migration audit: cross-Workspace reuse (#105/#106)

The maintainer authorizes auditing and closing remaining migration gaps, starting
with cross-Workspace reuse, and one reviewed commit directly to main after
validation. Development remains at 0.9.18. Production inspection, deployment,
live-data migration and public Wiki publication are separate.

## Acceptance and public test boundaries

- Preserve ordinary MSP library reuse without requiring template enrollment.
  Retain existing Document/Block opt-ins or exact client-listing primary reuse;
  source type does not imply enrollment. Require the same tenant,
  exact consumer placement, selected audience, live/pinned mode and source
  revision. Never grant access to the rest of a source repository.
- Preserve per-occurrence live and pinned selection, including distinct pins and
  source bodies with children. A reused block contributes its body, not the
  source document's child placements. Missing historical pins must be retained
  from immutable revisions with reviewed custody, never reconstructed from PDFs.
- Copying leaves legacy authority. Promotion and rollback cover the complete live
  source/consumer closure, require permission in every Workspace, reject stale
  reviews, and atomically restore authority and Git references after failure.
- Preserve all existing signed publications, PDF bytes and managed-file versions.
  New signed proof names ordinary library sources truthfully and cannot be
  inserted under historical template-only formats.
- Verify inventory, guarded import/preview, content reads, publish/history/PDF/file
  downloads and operator handoff under the constrained runtime database role.
  Include denied, cross-client and cross-tenant cases; missing Git fails closed.
- Verify recovery and schema reverse/reapply locally in the existing tekdocs
  services. Hosted validation must establish independent encrypted restore and
  fresh/supported upgrade paths on the exact pushed source.

The audit also examines remaining pin-history, nested-reference, relationship,
mapping and retention blockers. Record valid unsupported cases explicitly and
close them before claiming migration coverage complete. Invalid scope, missing or
corrupt custody, archived sources and resource bounds remain fail-closed gates.

## Reproduction

Legacy `blocks_for_library` admits explicitly shared non-template MSP blocks to
client reuse. `owned_placement_tree` currently permits foreign references only
when `template_enrollment_evidence` names their placements. A valid ordinary
library reference is therefore reported as `cross_workspace_reference` before
import. Tests exercise this existing inventory/import boundary before changing it.

## Status

The [audit ledger](remaining-migration-audit.md) records other valid shapes and
intentional fail-closed prerequisites. Implementation and both source-review axes are complete for this continuation.
All 704 combined Docker cases and nine final browser/server journeys passed,
including retained bytes, isolation and authority round-trip. Exact-source hosted
Build, CodeQL, upgrade and independent restore evidence remain required on the
pushed development commit. Other audit entries remain open; 1.0 completion is
not claimed.
