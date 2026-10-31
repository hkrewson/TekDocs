# Diagram-bearing publication migration

Next bounded #105/#106 slice, authorized after content-key runtime `781f1ad`.
The maintainer requests preserved diagram revisions, signed publications, PDFs,
all managed-file versions, rollback and recovery, followed by direct-main commit
and push when validation passes. Version remains 0.9.16. No release, production
migration, deployment or Wiki publication is part of this development slice.

Acceptance at the existing migration, read, publish/download, browser and
upgrade/recovery interfaces:

- Copy and promote the supported document composition with canonical Mermaid
  source intact. Preserve all legacy block revisions and immutable historical
  diagram SVG/PNG artifacts, signatures, control events, PDFs and file versions.
- New internal publications render the accepted Git composition, including
  diagrams supplied by supported shared/template/content-key sources. Freeze
  sanitized SVG and deterministic PNG with source/renderer/checksum evidence.
  Earlier signed bytes remain independent of later edits or renderer availability.
- Missing/corrupt retained diagram artifacts block migration and rollback;
  required renderer or source failure blocks new publication before retained rows
  or files are created. Existing tenant, client, file and MFA boundaries apply.
- Rollback projects current Git source while retaining all earlier revisions and
  signed artifacts. Re-promotion, fresh/0.8.46 upgrade and independent encrypted
  recovery verify the same custody invariants.
- Keep contracts, architecture decision, tests, roadmap, development notes, Wiki
  draft and risk dispositions aligned; complete two-axis source review and the
  strongest relevant local Docker gates before pushing. Bind hosted results to
  the exact runtime source.

Use only the existing `tekdocs` Compose project and its separate test database
locally. Independent upgrade/recovery stacks remain hosted-only. No broader
client delivery, cross-Workspace reuse or new diagram family is included.

Status: implementation and both source-review axes are complete. Local Docker
validation passed; exact-source hosted validation remains pending. The
[source-review record](../releases/diagram-source-review.md) preserves actual
reproductions and their corrections.

## Local validation and hosted boundary

**Verified:** the strongest migration Make selection, adapted to existing Docker
services, plus adjacent diagram/document/read-failure suites passed **524 cases**
with **two existing opt-in renderer-runtime skips**. Three additional template
and invalid-source cases passed afterward, covering all **33 diagram cases**.
The extra template test first omitted mandatory history retention; after using
that existing public preparation step, its unchanged certificate/custody checks
passed. No application gate was weakened.

All **four real browser journeys** passed, including actual retained-image
loading and mobile width, SVG/PNG and file download hashes, correction, withdrawal,
history and PDFs. Server-side retained-byte verification and authority rollback/
re-promotion passed, as did artifact hygiene. The distinct legacy diagram seed
asserts different source/SVG/PNG checksums and retains complete revision metadata.

Frontend validation passed **781 tests in 127 files**, types, lint, API drift,
build/budgets and license policy. Its audit has six existing low findings and no
moderate/high/critical finding. Script validation passed **128 checks** with three
existing opt-in skips. Ruff, mypy (291 files), no schema drift, exact OpenAPI
comparison, configured Bandit, version/pin/renderer contracts, product/language/
responsive checks, Compose contracts and local Wiki links passed. Both independent
source reviews have zero remaining findings. The reviewed failure reproductions
remain in the source-review record.

**Inferred only:** these results validate bounded development behavior, not
production operator acceptance, deployment, a new release or aggregate 1.0
readiness. Existing CSP/COEP/KaTeX ownership and expiry, and open development-tool
advisories, are unchanged; no exception is accepted or renewed.

**Blocked locally:** independent fresh/0.8.46 upgrade, encrypted restore and
production-image stacks are prohibited by the single-project rule. Required
exact-source hosted Build, CodeQL and Extended gates must supply these results.
The two skipped opt-in renderer checks must also be confirmed by the hosted
renderer rehearsal rather than inferred from local unit selection. A required Wiki
page is drafted locally in the separate checkout and remains unpublished.
Ignored AGENTS files remain private. No source commit or hosted completion is
claimed until its identity and receipts are recorded.
