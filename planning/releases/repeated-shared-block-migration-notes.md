# Repeated shared-block migration development notes

Baseline: published 0.9.18 `81fed48f`. The maintainer authorizes implementation,
validation, review and direct-main commit/push. No new version, release images,
production deployment, live-data migration or Wiki publication is part of this
slice. [Acceptance](../migrations/repeated-shared-block-migration.md) is #105/#106.

## Behavior

Migration tracks each same-Workspace shared-leaf reference by placement identity,
ordered position, audience and live/pinned mode. Two pins of one Block retain
separate commits/digests. Previews expose per-occurrence descriptors; copied-node
identity remains deduplicated while composition and source proof retain every
occurrence. Current source/owned files are never replaced by a selected old pin.
Prior pin matching uses the exact parent include ordinal rather than the first
matching Block UUID, preserving rollback and repeat-copy verification.

New repeated-source publications use signed v12 envelopes over their existing
v7-v11 content/diagram certificates. Signatures cover the original envelope.
Offline verification and normal reversible Django migration 0213 admit repeated
identities only for this new format while retaining unique ordered paths, exact
indexed source proof, audience, file, key and template guards. Historical formats
retain their original unique-source constraint; no retained manifest, signature,
PDF or file version is rewritten. API fields/paths, schema fields and dependencies
are unchanged; the preview command adds placement/mode/audience/path descriptors.

Pins must already be represented by exact retained accepted Git history. The
synthetic upgrade/recovery cohort explicitly prepares that prerequisite from its
retained legacy revisions before copying the consumer. Missing represented
history remains a blocker; no PDF regeneration or inferred pin is used. Repeated
owned Block structures, general cross-Workspace reuse, missing/corrupt history and
broader structural authoring remain outside this slice.

## Reproductions and verification

- Verified initial red: separate live/pinned occurrences were rejected at guarded
  import as unsupported_placement_graph (`tekdocs-repeated-red.log`).
- Verified second red: distinct pinned editions copied/promoted, then the existing
  SQL publication guard rejected repeated identities (`tekdocs-repeated-publish-red.log`).
- Both tracer cases pass after occurrence bookkeeping and v12 guard changes.
- New harness corrections preserve application boundaries: runtime service tests
  bind their explicit user/Workspace RLS context; the publication-bearing importer
  intentionally reports its broad publication_parity_required guard before the
  underlying missing-pin export reason. Neither required an application relaxation.

Standards review: zero actionable findings. Spec review: zero actionable findings.
Backend Ruff, strict mypy (293 source files), migration consistency, Bandit and
byte-identical OpenAPI regeneration passed. The combined focused repeated/shared
Docker gate passed 45 cases, including constrained runtime role, SQL reverse/reapply,
audience separation, late rollback failure and retained downloads without Git.
The adapted document-migration/authoring gate passed 644 cases across 22 modules
in 31m31s. A final 17-case run passed with full Block/file metadata recovery
checks and the v12/v11/v10 content-key/diagram combination. All 795 frontend
cases, API/lint/types/build/budgets and seven diagnostic contracts passed.
The strongest local publication browser Make gate passed all eight real journeys
with zero retries (2.5m), retained-byte/server authority round-trip verification and
artifact hygiene. Hosted fresh/0.8.46 upgrade and independent encrypted-restore
evidence remain mandatory on the pushed exact source.
The strongest relevant document-migration-release-gate provisions independent
upgrade/recovery/production environments; those portions must run in hosted CI.
Local validation uses only existing tekdocs services and generated test databases
inside its existing PostgreSQL service. No retained development data is removed.

The native source-secret scan passed with the pinned scanner version and existing
reviewed policy. Its initial six matches reproduced a host-path translation issue:
all six exactly matched existing /src rule/line fingerprints. Only the temporary
export's path prefix was translated for native execution; repository ignores and
source were unchanged. Ignored runtime/agent files were never exported.

Schema reverse/reapply preserves signed rows under the current application; it
does not claim an older binary can interpret new v12 certificates. Authority
rollback and network-isolated recovery are the supported rollback/recovery seams.

Existing CSP/COEP/KaTeX findings and separate development/build-tool advisories
retain their existing owners and bounds. This development slice renews none of
them and does not claim final 1.0 security or human acceptance. Original
notification/browser causes retain their investigation obligations in the failure
ledger.
