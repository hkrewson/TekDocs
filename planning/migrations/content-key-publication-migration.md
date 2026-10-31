# Content-key block substitution migration

Continuation of #105/#106 from `d8f75b4`, explicitly including content-key block
substitution in the user's scope reply. The completed field-key slice remains
historical evidence; this continuation has its own validation and review.

Acceptance uses the agreed migration, document read/publication, browser and
upgrade/recovery interfaces:

- Migrate consumers and the reusable block dependency graph together, preserving
  binding identities, exact source revisions, authored expressions and nested
  field/content keys. Content keys retain their existing current-revision
  semantics; ordinary pinned placements retain their selected revisions.
- Git-authoritative reads, current editable exports and publications use accepted, current Git block
  content, with no fallback to retained SQL Markdown. Keep permission and exact
  Workspace boundaries, limits, cycle checks and explicit unavailable states.
- New publications retain independently verifiable frozen substitution proof.
  Existing signed publications, PDFs and all managed-file versions remain exact
  through subsequent Git edits, withdrawal, authority rollback and recovery.
- Reject incomplete dependency handoff, stale previews/indexes, missing or
  denied sources, malformed/inline substitution, cycles and limit violations
  without partial authority, Git, SQL or artifact changes. Serialize writers
  against authority transitions.
- Keep API contracts, tests, architecture decision, roadmap, development notes,
  Wiki draft and known-risk disposition aligned. Complete both required source
  review axes and local Docker validation before the authorized direct-main push;
  bind required hosted upgrade/recovery receipts to the tested source.

Use the existing `tekdocs` Compose project and isolated test database only.
Independent fresh/upgrade/encrypted recovery environments remain hosted-only.
General cross-Workspace content-key reuse, client delivery and diagrams remain
outside this continuation. Version stays 0.9.16; no release, production change or
Wiki publication is authorized here.

Status: implementation and both source-review axes are complete. All 65 focused
Docker cases and three real browser journeys plus server-side custody/rollback
verification passed. The final combined migration/key/read/evidence regression
passed all 496 cases. Exact-source hosted gates passed at `781f1ad`; the
final receipt below establishes the completed bounded development slice.
The [source review](../releases/content-key-source-review.md)
records reproduced corrections and retracted candidates. No production acceptance
or aggregate 1.0 readiness is claimed.


## Local validation and hosted handoff

**Verified locally:** the strongest migration Make gate, adapted to the existing
Docker services, plus adjacent key resolution, binding API, read, composition and
publication-read failure cases passed **496 cases**. The focused content-key file
passed **65 cases**. All three real HTTP/browser publication journeys and their
server-side custody and group rollback/re-promotion checks passed. Frontend
validation passed **778 unit tests**, types, lint, build/budgets, API contract and
license checks. Script validation passed **128 checks** with three existing
opt-in skips. Ruff, mypy (290 files), schema drift, exact OpenAPI comparison,
Bandit, runtime dependency audit and local Wiki links passed. No new dependency
is introduced. Standards and Spec source reviews each have zero remaining findings.

The source-review record preserves the reproduced inline-substitution, stale
editable-export and plain-composition capacity defects and their corrections.
The old self-cycle test was updated only after reproducing the more specific
cycle refusal. Rejected operations still require no partial authority or files.

**Inferred only:** these local results establish the bounded development
behavior, not independent encrypted recovery, production acceptance or 1.0
readiness. Existing CSP/COEP/KaTeX dispositions and the open development-tool
advisories retain their ownership and expiry; no acceptance is renewed here.

**Blocked locally:** independent-stack fresh/upgrade and encrypted restore gates
are prohibited by the single-project rule. They passed in hosted CI against
runtime source `781f1ad95cb456d9a226cfdecad6a5adcb697b1a`:
[Build](https://github.com/hkrewson/TekDocs/actions/runs/41213064315),
[CodeQL](https://github.com/hkrewson/TekDocs/actions/runs/41213066706) and
[Extended validation](https://github.com/hkrewson/TekDocs/actions/runs/41213068455).
The exact-source results and downloaded evidence were checked, completing these
required gates. The required Wiki page is a local, unpublished draft; ignored
AGENTS files remain private. No version, image release or production change
is claimed.


## Final exact-source receipt — October 31, 2026

**Verified:** runtime `781f1ad95cb456d9a226cfdecad6a5adcb697b1a` passed
[Build 41213064315](https://github.com/hkrewson/TekDocs/actions/runs/41213064315),
[CodeQL 41213066706](https://github.com/hkrewson/TekDocs/actions/runs/41213066706)
and [Extended 41213068455](https://github.com/hkrewson/TekDocs/actions/runs/41213068455).
All fifteen PostgreSQL groups passed, including all **65 content-key cases**;
merged backend coverage is **89%**. Frontend, all five browser groups, performance,
DAST, production image/SBOM/vulnerability policy and diagram checks passed.
The three hosted real publication journeys and server-side retained-byte and
authority rollback/re-promotion checks passed.

The upgrade log confirms the content-key graph, signed publications, file
versions, PDFs and rollback on both fresh and 0.8.46-upgraded data. The independent
network-isolated encrypted restore confirms these retained inputs recovered
exactly, including the fixture's control-event fingerprints. All eight historical
upgrade paths and versioned diagram upgrade also passed. Downloaded CodeQL,
browser, DAST, access-boundary, dependency/license/secret, image, upgrade, recovery
and diagram evidence records name this exact source and passed status.

An additional earlier documentation-only Build at `d8f75b4`
([41189551693](https://github.com/hkrewson/TekDocs/actions/runs/41189551693))
had timed out awaiting creation from a template in the existing 120-second live
journey. The original cause remains **unknown**. The complete local and hosted
journeys subsequently passed, with no selector, assertion, timeout or retry
weakened. This is a successful retest, not a demonstrated fix. The original
failure and disposition remain in the validation ledger. No new-source hosted
failure or corrective runtime commit was required for this slice.

**Inferred only:** this completes the bounded development contract, not production
operator acceptance, a release, general cross-Workspace reuse or aggregate 1.0
readiness. The existing development-tool advisories remain open before 1.0; no
risk allowance is accepted or renewed.

**Blocked locally:** independent-stack gates were left to hosted CI as required;
those exact-source gates are now complete. The Wiki update remains an unpublished
local draft. No required runtime gate remains pending for this source. Later
evidence-only commits retain this tested-source identity and make no new runtime
claim.
