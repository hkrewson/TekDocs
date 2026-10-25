# Mixed-authority document listing regression

October 25, 2026. Bounded #105 follow-up after the first per-document handoff.

Acceptance: the standard document list must retain authorized legacy documents
when another document in the same Workspace becomes Git-authoritative. Empty
search and text search must agree on visibility; counts, pagination, exclusions
and existing permission boundaries must remain correct.

## Reproduction and correction

The operator reported that an unmigrated publication-bearing guide disappeared
from the unfiltered list, whose total became one, while searching its title
still returned it. Read-only inventory confirmed its legacy row and placement.

An isolated Docker/PostgreSQL regression creates two synthetic documents,
verifies both are listed, imports and promotes one through the real handoff,
and queries the authenticated document-search endpoint. Before the fix, search
finds the remaining legacy guide but empty search fails `assert 1 == 2` for
the total. Reproduction: `sh /tmp/tekdocs-mixed-list-repro.sh runtime`; retained
local log: `/tmp/tekdocs-mixed-list-before.log`. An earlier fixture attempt
stopped at `repository_index_not_current`; initializing the synthetic index
corrected that prerequisite without changing runtime code.

The empty-query branch returned only canonical repository records before
collecting legacy matches. It now combines both sets before the existing
sorting, facets and pagination. Both paths retain the existing scoped queries;
no permission grant, document mutation, migration or API schema change is added.

Release note: fixes legacy documents disappearing from the default Documentation
list after promoting another document to Git. Search remains available as a
workaround on v0.9.13. No production rollback or content recreation is required
by this listing correction.

## Verification and delivery

Verified: the pre-fix Docker reproduction catches the reported symptom. Wiki
guidance is drafted in the local Wiki checkout and its page/link check passes.
The same post-fix Docker regression passed (1 passed in 55.68 seconds), including
the combined total and second-page result. Log: `/tmp/tekdocs-mixed-list-after.log`.
The final test also covers exclusion, empty-result search and template filtering.
Final Docker validation passed `make test-document-migration-inventory` (29
tests) and `make test-documentation-validation` (1,749 passed, one skipped),
using the normal Make targets through a temporary adapter that directs Compose
to a fresh isolated project. Log: `/tmp/tekdocs-mixed-list-gates.log`.
The existing malformed-UUID parametrization selects zero cases (confirmed by a
Docker inspection of its selection expression), explaining the skipped case;
this change neither adds nor repairs that separate coverage gap.
Ruff passed and mypy reported no issues in 270 source files. The final diff and
`make wiki-check` passed. The adapter retained the normal test selections and
cleaned up only its own containers, volumes and images.

Verified: the defect and correction at the authenticated API boundary under
Docker/PostgreSQL, plus the existing route-permission and runtime-isolation
gates. Inferred: the corrected response restores the production UI because
that UI consumes the tested search endpoint for both browsing and searching.
Production verification remains pending deployment. No new dependency,
authorization policy or accepted security exception is introduced.

Release delivery remains pending: this is a local correction, not a new release
candidate. A versioned release still needs source/risk review and exact-candidate
hosted Build, CodeQL, extended validation and image publication gates before
production update. The full document-migration release rehearsal was not rerun
for this read-list-only change; no new migration or recovery behavior is claimed.

The production promotion succeeded separately. Its original content display
and editing smoke checks still need operator confirmation. The separate
publication-bearing guide remains ineligible for migration; this correction
does not change that boundary.
