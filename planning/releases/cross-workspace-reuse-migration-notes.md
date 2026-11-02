# Cross-Workspace reuse migration development

The maintainer authorized a remaining-gap audit beginning with cross-Workspace
reuse, preserving signed publications, PDFs and file versions, with isolation,
rollback/recovery and a reviewed direct push to main. Baseline is `cac36757`;
version remains 0.9.18. [Acceptance](../migrations/cross-workspace-reuse-migration.md)
and [ADR 0123](../../docs/adr/0123-cross-workspace-library-custody.md) define this
bounded continuation. Production migration and Wiki publication are separate.

## Reproduced gaps and corrections

- A valid non-template MSP shared block failed the existing import entry point
  with `cross_workspace_reference` and `cross_document_source_unavailable`.
- Follow-up public-boundary regressions reproduced listing-authorized reuse,
  unenrolled reuse from a template, indexing a source with its own dependency,
  unsafe source-file links and nested field-key/repeated-source publication
  validation. All five initially failed without loosening existing assertions.
- A v13 publication initially blocked authority rollback as unsupported retained
  history. Both retained-history checks and the shared repetition predicate now
  understand the new envelope while preserving old-format rules.
- The restricted-role regression reproduced unshared ordinary sections becoming
  visible through a source Document. Source projection now distinguishes library
  opt-in, template blueprint and exact client-listing visibility; foreign reads
  no longer confer placement or Block writes.
- An occurrence-level regression reproduced selecting the other retained pin of
  the same Block at the first ordinal. The loader now checks each pin at its
  actual parent/ordinal; the template reader selects only enrolled placement IDs.
- A source created before Git storage configuration raised an uncaught missing
  repository exception. It now reports an import blocker without a partial copy.
- The browser follow-up reproduced a stale foreign-LIVE composition during direct
  publication after a source edit. Refreshing only the consumer cache made the
  focused reproduction pass. Publication now performs the same custody-checked
  refresh while all source/consumer heads are pinned, before freezing its proof.
  No prior reader request is required.
- Final review reproduced incomplete repository-wide publication pin discovery
  and omitted legacy foreign pin owners. Discovery now covers the full refreshed
  include scope and is fenced again after acquisition. The pinned dependency
  check rejects incomplete promotion and source rollback that would strand a
  promoted client. Single-document and raw SQL rollback bypasses both reproduced
  before adding the common preflight and a serialized deferred database guard.
- A trusted same-Workspace service call had no ambient tenant scope, so the new
  preflight initially rejected it. The existing handoff test reproduced that in
  3.11 seconds; an explicit-scope probe passed. The existing six-setting
  bind/restore context is now shared through an edit-policy-checked helper,
  preserving ordinary no-MFA service behavior and protected template/MFA gates.
- Single-document library sources and consumers without signed history initially
  bypassed MFA. Both negative tests reproduced the bypass. Authorization now runs
  before Git access and again after owner/Block locks, using an exact-Workspace
  boolean classifier that sees hidden foreign participants without returning IDs.
  A separate-connection NOWAIT probe reproduced missing source-Block locking;
  owned Blocks are now locked before the authorization recheck.
- Combined validation reproduced read-only denials returning the wrong service
  exception. A handoff adapter preserves the established domain error while
  keeping the centralized denial and pre-Git gate. Four focused cases passed.
- Historical addressed/content-key/occurrence guard tests invoked the current
  publisher against older schemas, reaching missing columns/functions before the
  intended guard. The occurrence test's broad exception check hid that boundary.
  Direct SQL reinsertion now preserves every signed byte/identity: the current
  guard accepts the certificate before uniqueness rejects it, while the older
  guard must reject its format first. Migration head is restored in `finally`;
  signatures and PDF bytes remain checked across the cycle.
- The combined run reproduced a template rollback test that expected the later
  LIVE SQL barrier after a new pinned preflight had already rejected the service
  call. Three strict cases now cover the source service, live-client service and
  direct source SQL barrier, checking every root/fragment authority and unchanged
  signed manifest, signature and PDF after rejection.
- An assigned client editor could read an approved source but could not take an
  UPDATE lock on it after the foreign read/write policy split. Live and pinned
  enrollment both reproduced the failure. Foreign reuse now uses the existing
  placement trigger's source lock and rechecks availability/authority under that
  lock; local sources retain their explicit lock. Tests prove source UPDATE is
  denied, a separate connection cannot lock the source and its head is unchanged.
- Client RLS hides the source fragment's authority row. Ordinary pinned reuse
  initially accepted that Git-owned source's database revision cache. Four
  same/new-client live/pinned cases reproduced the missing service barrier. The
  guard now also checks the approved source-root authority in its exact Workspace;
  controlled template operations retain their explicit exception. Nine focused
  reuse/authority/isolation cases passed after correction.
- Failure-only server diagnostics retain bounded code locations and fixed
  categories, excluding exception messages, locals and request values. An early
  plugin exposed installed/local package mismatch under the console launcher;
  collection reproduced it and the Python-module launcher resolved it.
- The initial missing-storage test targeted the metadata endpoint, which correctly
  returns metadata with no legacy body. The regression now targets the canonical
  Git-content endpoint, retaining the 409/no-database-fallback and recovery checks.

## Preservation and policy

Foreign reads remain single-fragment reads through exact retained sharing proof.
Sources and consumers are imported explicitly; history retention has its own
reviewed fingerprint. Authority transitions require the complete connected group,
per-Workspace edit/MFA authorization, matching Git/index state and unchanged
signed/file custody. Failure after both document transitions restores every
authority row. Missing Git remains retryable and never substitutes database text.

New v13 certificates distinguish ordinary source Block revisions from enrolled
template definitions, including mixed occurrences of one source Block. Signed
records, source revisions, PDFs and file-version chains are append-only. The
standalone synthetic fixture is also delivered through fresh/0.8.46 upgrade,
browser/server custody and independent encrypted recovery paths.

## Evidence status

Verified local Docker: all 704 combined migration/authoring cases passed across
23 modules in 38m23s, including forced-RLS isolation, complete authority closure,
rollback/failure recovery, retained signatures/PDFs/file versions and schema
reverse/reapply. The single warning comes from the intentional duplicate-ZIP
negative test. Earlier failing/interrupted runs are not recorded as passing gates.

Verified final Docker browser/server gate: all nine real Chromium journeys
passed after all source corrections (3m12s of UI cases), followed by retained-byte
verification and authority round-trip. Coverage includes publishing, corrections,
withdrawal, history and PDF downloads. Artifact hygiene passed. The initial
UI-only pass with a failing server follow-up is not a passing acceptance gate.

Both source-review axes have no remaining actionable findings. Frontend
API/lint/types, all 795 cases, bundle budgets and seven privacy-diagnostics cases
passed. Host tooling passed 143 cases (three optional skips). Final mypy passed
300 source files; Ruff and Bandit are clear. The final Git-visible source scan
checked 1,593 files with no unignored secret findings. OpenAPI matches, Django
reports no missing migrations, and documentation/Compose/supply-chain contracts
passed. No AGENTS file is tracked or included in this change.

Exact-source Build, CodeQL and Extended validation artifacts must confirm hosted
fresh/supported upgrade, production-image and independent encrypted recovery on
the pushed development commit. Those local scripts create additional environments
and therefore run only in hosted CI; local work reused the existing tekdocs
services and generated test databases inside its retained database service.
Version remains 0.9.18; this does not prepare or deploy another runtime release.

Inferred: compatibility outside the explicitly tested compound publication shapes
is not established by these results. General structural or parameterized foreign
source completion is not claimed. Blocked prerequisites, valid open shapes and
configuration/data issues remain in the audit ledger. Existing security-risk
decisions, tooling advisories and unknown historical browser causes are unchanged;
formal final 1.0 security acceptance is separate. The required Wiki update is a
local draft; public Wiki publication and production migration are separate.
