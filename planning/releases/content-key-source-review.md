# Content-key continuation source review

Fixed baseline: `d8f75b48e3f86fd8fc771a4bff2036191e1116c6`. Review includes the
working changes, new source/tests/fixtures and proposed ADR 0118 before the
authorized direct-main commit. No PR, version bump or production change is included.

The code-review skill's independent, read-only Standards and Spec reviews were
repeated after runtime reproductions and corrections. Review does not substitute
for runtime validation. Complete local/backend/browser validation subsequently
passed. Exact-source hosted gates subsequently passed at `781f1ad`; the
slice record links the complete receipts.

## Standards

Standards re-review: **zero remaining findings**.

The ordinary uncopied-consumer regression confirms that existing authority rows
let the SQL closure reject split handoff; the earlier premise remains retracted.

The latest corrections enforce standalone substitution placement through the
shared validator and use accepted Git content for current exports. Portable v4 is
selected only for retained Git content-key proof; existing legacy and field-only
v3 output remains unchanged. Using the retained commit timestamp preserves
deterministic export provenance.

The older repository-evidence path continues to reject unsupported content-key
evidence without leaving rows or files. Correction/withdrawal coverage and retained
control-event fingerprints strengthen lifecycle verification.

No additional documented-standard breach or actionable heuristic smell found.
The subsequent 496-case backend regression and three browser journeys passed.
Hosted upgrade and recovery subsequently passed at `781f1ad`; those results
come from their independent receipts, not from this review.

## Spec

Spec re-review: **zero remaining concrete findings**.

The shared validator now rejects inline substitutions, and Git-owned exports
resolve current Git content with appropriate proof and timestamps. Legacy
formats and repository-evidence refusal remain intact. Correction, withdrawal
and control-event preservation are covered by the fixture.

Subsequent complete local and exact-source hosted runtime validation passed;
the slice record links the receipts.

## Reproductions and disposition

- Valid, acyclic inline substitutions were accepted by protected Git writes and
  migration preview. Three public-interface cases reproduced this. The shared
  migration/write walker now applies the maintained freezer's standalone-line
  and parsed-occurrence semantics. These cases pass without accepting Git changes.
- Current editable exports read retained SQL source text after a Git source edit.
  Two MSP/client cases reproduced the stale result. Git-owned exports now pass
  the accepted repository into the maintained freezer and retain Git proof in
  portable v4. Legacy/field-only portable v3 behavior remains unchanged.
- A review candidate assumed uncopied Documents lack authority rows. Service
  creation and migration 0192 already create/backfill those rows. The ordinary
  uncopied-consumer SQL regression passes unchanged; no speculative SQL fix made.
- A supplemental candidate predicted unsupported repository evidence insertion.
  The public service already refuses it at `repository.render.unavailable`, before
  signing or insertion. The regression verifies no new row or retained file.
  The candidate was retracted; no speculative format opt-in was added.
- The first complete migration run had 373 cases: 372 passed and the older
  content-key deferral test failed because its self-cycle now returns the more
  specific `content_key_cycle`. Its name and expected code were updated after
  inspecting the actual failure. Rejection remains required. The final complete
  corrected-source run subsequently passed all 381 cases.
- A further boundary probe found the new content walker applying its 2 MiB
  expansion limit to plain source compositions with no content key. A supported
  three-fragment composition between 2 and 4 MiB reproduced the refusal. The
  walker now returns early for non-content-key bodies, preserving existing
  binding/field/scope checks and composition capacity. Both reviewers cleared
  this correction; all 65 focused content cases and all three real browser
  journeys plus server-side custody/rollback verification passed. The final
  complete migration selection with adjacent key/read/evidence cases passed all
  496 cases.

Final source-review count: Standards 0, Spec 0. No remaining finding on either axis.
