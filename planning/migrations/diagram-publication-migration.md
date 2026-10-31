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
validation and exact-source hosted validation passed at `5b7a9314`. The
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
production-image stacks are prohibited by the single-project rule. Exact-source
hosted Build, CodeQL and Extended gates supplied these results. The hosted
renderer rehearsal also passed deterministic-byte, sandbox and cleanup checks;
the skipped local runtime checks are not treated as unit-test passes. A required Wiki
page is drafted locally in the separate checkout and remains unpublished.
Ignored AGENTS files remain private. Exact runtime source and checked receipts
are recorded below; no required hosted gate remains pending for this runtime.


## Final exact-source validation — October 31, 2026

**Verified:** runtime `5b7a9314866156ad731ee6e3c49c921b437a8e0a` passed every
required hosted workflow:

| Gate | Exact-source receipt | Result |
| --- | --- | --- |
| Build, test, and secure | [41228928621](https://github.com/hkrewson/TekDocs/actions/runs/41228928621) | All sixteen PostgreSQL groups, all 33 diagram cases, 89% merged backend coverage, frontend, four live publication/browser journeys with server custody and authority round-trip checks, renderer determinism/sandbox/cleanup, production images, SBOMs and vulnerability policy passed. |
| CodeQL | [41228934806](https://github.com/hkrewson/TekDocs/actions/runs/41228934806) | Both languages and the downloaded commit-bound receipt passed. |
| Extended validation | [41228937218](https://github.com/hkrewson/TekDocs/actions/runs/41228937218) | All five browser groups, DAST, performance, eight historical upgrade paths, fresh/0.8.46 document migration, versioned diagram upgrade, independent encrypted recovery and final evidence delivery passed. |

The upgrade log confirms diagram revisions, signed graphics, file versions, PDFs
and rollback on both fresh and 0.8.46-upgraded data. Legacy publications were
created by the old publisher using the maintained isolated renderer in the same
rehearsal project. Its two seeded graphs have distinct source/SVG/PNG checksums;
all original block revision metadata and signed artifact bytes remain retained.
The independent network-isolated encrypted restore confirms these revisions,
SVG/PNG, files and PDFs recovered exactly, including signed manifests, control
events and Git object fingerprints. The hosted four-journey acceptance also
confirmed graphic loading, download hashes and authority rollback/re-promotion.

Downloaded CodeQL, browser, DAST, access-boundary, dependency/license/secret,
image-scan, upgrade, recovery and diagram upgrade/restore evidence records all
name this exact source and passed status. No receipt is inferred from a different
source or a cancelled run.

The application feature is `d8e9b392`; the only subsequent runtime-source delta
in `5b7a9314` supplies the same renderer setup to the supported combined-core
runner. Both review axes cleared that corrective delta. Initial-source runs
41228633907, 41228636478 and 41228638894 were intentionally cancelled as
superseded and remain recorded as cancellations, not failed tests or passes.
No selector, assertion, retry or timeout was weakened.

**Inferred only:** this completes the bounded development slice, not production
operator acceptance, deployment, a new release, general cross-Workspace reuse,
client delivery or aggregate 1.0 readiness. Version remains **0.9.16**. Existing
CSP/COEP/KaTeX ownership and expiry, and open development/build-tool advisories,
are unchanged; no exception is accepted or renewed.

**Blocked locally:** separate-stack gates were left to hosted CI as required.
Their exact-source results are now complete; no required runtime gate remains
pending. The required Wiki update remains a local unpublished draft, with
pre-existing edits preserved. Later evidence-only commits retain this tested
runtime identity and make no new runtime claim.
