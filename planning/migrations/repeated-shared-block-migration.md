# Repeated shared-block migration (#105/#106)

The maintainer authorizes migration of repeated shared blocks, including different
pinned versions, after published 0.9.18 (`81fed48f`). Commit and push directly to
main after validation. This is development at 0.9.18, not a new version or
production deployment.

## Acceptance

- Preserve every supported same-Workspace shared-leaf occurrence in placement
  order, including mixed live/pinned references and distinct pins of one Block.
  Stable Block identities must not collapse occurrence-specific source proof.
- Keep each pin bound to its own retained Git object. Current live changes must
  propagate only to live occurrences, including after rollback and re-promotion.
- Preserve existing signed publications, retained PDFs and all managed-file
  versions byte-for-byte. New publications bind the complete ordered occurrence
  proof; historical signed format constraints remain unchanged.
- Retain scoped authorization, audience narrowing, exact-source/index checks,
  bounded history/composition limits and atomic live dependency groups. Refuse
  stale plans, missing pins, ambiguous owned structure and corrupt retained files
  without partial authority or publication state.
- Verify the existing import/status, publication/read/download, real browser,
  rollback and independent encrypted recovery boundaries. Local tests use only
  the existing tekdocs services and generated test databases in its database
  service. Fresh/0.8.46 upgrades and independent restore run in hosted CI.

General cross-Workspace reuse and arbitrary structural authoring remain outside
this slice. Existing template-library authorization boundaries stay intact.
Production data changes and public Wiki publication require separate authority.

## Evidence

Implementation, both source-review axes and local validation are complete: 644
migration/authoring cases, 17 final preservation/compound cases, 795 frontend cases
and eight real browser/server journeys. [Development notes](../releases/repeated-shared-block-migration-notes.md)
record reproductions, scoped risks and local Docker evidence. Exact-source hosted
fresh/0.8.46 upgrade and independent encrypted restore remain completion gates. The first regression exercises
the existing guarded import entry point with separate live and pinned placements
of the same source Block; its pre-change rejection is the baseline reproduction.
