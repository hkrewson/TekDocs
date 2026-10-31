# Monitored-source migration source review

Baseline: `ab48a667727b80b2111e97e606755f5a3d072e79`. The review compares the
bounded working patch and new files with that fixed baseline, including ADR 0120,
the public API, frontend, SQL custody checks and standalone hosted fixtures.
The maintainer's request and
[slice acceptance](../migrations/monitored-source-publication-migration.md)
are the specification. Runtime receipt identity remains separate from source
review; the final tested commit is recorded in the slice closeout.

## Standards

The independent read-only review initially found two actionable issues:

- Source-check response serialization acquired Git after retaining a source-row
  lock. A public HTTP reproduction under a held repository pin confirmed that
  checking waited for Git while holding the source. Check responses now defer
  Git review to a separate listing request, preserving Git→repository→document→source
  lock order for reviewed writes. The contention regression passes without
  changing the lock timeout or weakening its completion requirement.
- Still-legacy apply tried to authorize a Git write when called inside an outer
  SQL transaction. The pre-promotion public service reproduction raised
  `RepositoryInputError`. Lock acquisition now enlists read-only; the actual
  authoring writer continues to enforce coordinated outer write ownership.
  The legacy nesting regression and Git transaction-compensation tests pass.

The review also identified confusing apply-review statuses on failed observations.
A panel reproduction confirmed the extra status; the interface now presents
apply blockers only for actionable changed, unapplied observations. The review
was repeated after these corrections and reported zero actionable findings.
A final narrow review then identified missing live-reuse disclosure. The panel
now displays an explicit translated notice covering live propagation and retained
pinned/signed content before apply. It shows no incomplete consumer counts or
restricted names. Its absence was reproduced, then covered by a passing panel
regression and browser assertion. Standards re-review again reported zero
remaining findings; editable primary fragments require no detach action.

## Spec

The independent read-only review found that a successful apply could be presented
as a mutation failure when the subsequent reader refresh failed. The public-client
reproduction confirmed the missing success acknowledgement and stale open review.
Apply success now closes that review and is acknowledged independently; a reader
outage uses the existing unavailable-reader state. Applied, refused and
refresh-failed cases pass.

The review requested explicit successful promoted polling evidence. Added tests
verify a new observation and schedule update, reloading saved settings from a
stale source instance, with unchanged Git/body, retained SQL revision, applied
pointer and signed artifacts. The source-check HTTP contention case and separate
frontend fresh-review request also pass. Re-review reported zero actionable
findings and no scope expansion.

## Additional reproduced corrections

An invalid all-zero UUID in the unowned-file negative fixture was ordinary inert
text under the maintained link parser. Its extraction returned zero attachment
identities; a valid synthetic UUID returned one. The fixture now uses a valid
random UUID and keeps the same `PlacementConflict` and no-partial-change assertions.
No parser, ownership guard, selector or rejection assertion was loosened.

A source custody test changed a timestamp from microsecond `100001` to `100002`
and reproduced an unchanged digest because Django's ordinary JSON encoder rounds
to milliseconds. Runtime and baseline-compatible recovery fingerprints now use
full ISO timestamp precision. The regression passes.

## Validation boundary

At re-review, all 32 focused Docker cases and 789 frontend tests passed, together
with API generation, lint, types, build/bundle, audit and license checks. The
initial 505-case migration/adjacent regression had 504 passes and the invalid-UUID
fixture failure above. Final full migration, real browser/server and exact-source
hosted upgrade/recovery receipts remain pending in the slice record. Source
review alone does not declare those runtime gates complete.

Summary: Standards zero remaining findings; Spec zero remaining findings. The
original findings and reproductions remain recorded independently of green retests.

Subsequent browser validation passed all five journeys and server-side custody/rollback
checks after requiring actual settings-save responses and ready controls. A controlled
deferred-save regression verifies the stale prior success message and busy navigation
guard. The slice record preserves the initial timeout and inferred cause boundary.
A further panel reproduction showed that a later unchanged check hid an unapplied
source change; successful pending observations now stay reviewable, with an explicit
awaiting-review label. Baseline-matching unchanged checks still offer no apply action.

Final local closeout: the combined migration/authoring gate passed 656 cases.
A large-history probe then reproduced excess cursor buffering (39,205,291 traced
peak bytes); smaller cursor batches pass the unchanged 24 MiB bound. All 34 final
source/transport cases passed after that resource correction. The final frontend
gate passed 793 cases, and all five final live browser journeys and server-side
custody/rollback checks passed with the impact notice. The source slice remains
pending its exact-source hosted Build, CodeQL, fresh/upgrade and encrypted-recovery
receipts. No existing risk exception is accepted or renewed.
