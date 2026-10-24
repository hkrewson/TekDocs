# Dependency security maintenance — October 23, 2026

Scope: resolve PR 111 Build run 40044545275's dependency-audit failure by
updating DRF and checking compatibility. The remaining security-job audits were
also reproduced locally before pushing; they identified additional DOMPurify
and renderer Zod blockers, included in this same remediation. Acceptance: the unchanged audit finding
reproduces, the updated lock passes without exceptions, Docker authorization
checks pass, and hosted Build confirms the dependency and API contracts.

## Reproduction and change

Docker pip-audit against the unchanged production lock reproduced three findings
in DRF 3.17.2: CVE-2026-114138, CVE-2026-114136 and CVE-2026-114137.
The [upstream 3.18.2 release](https://github.com/encode/django-rest-framework/releases/tag/3.18.2)
fixes oversized Accept-header handling, non-text encoding charsets and TokenProxy
deletion. [3.18.3](https://github.com/encode/django-rest-framework/releases/tag/3.18.3)
also corrects the content-negotiation precedence return value introduced in 3.18.2.

The requirement is now `djangorestframework>=3.18.3,<3.19`; both generated hash
locks select 3.18.3. No unrelated dependency version changed. DRF remains the
existing maintained BSD-licensed dependency; no new library is introduced.
No application schema migration, endpoint or permission change is intended.

## Evidence and limits

Verified: Docker audit of the updated production lock reports no known
vulnerabilities, without exceptions. The original three findings were reproduced
before editing. Local Docker runtime authorization passed 13 tests; hosted confirmation remains
pending. Published v0.9.11 images remain unchanged; this dependency fix requires
a new versioned release before production receives it. The current PR push
validates source and does not publish or deploy a release.

## Remaining dependency audits

Frontend DOMPurify 3.4.16 and renderer DOMPurify 3.4.13 reproduced critical
findings; both now resolve 3.4.17. Renderer Puppeteer 25.7.0 pulled Zod 3.25.76,
which reproduced a high-severity collection-validation memory-exhaustion finding.
Puppeteer is now pinned to 25.16.0 with its compatible dependency chain, including
Zod 4.6.7. Mermaid 11.16.1, CLI 11.16.0 and the Chromium 155 assertion are unchanged.

Both npm production audits now pass the existing high/critical threshold without
exceptions. Frontend retains six low-severity audit entries and renderer retains
five, stemming from KaTeX GHSA-238p-pmpm-9mq7 and its dependency chains. No zero-
vulnerability claim is made. The audit's proposed automatic remediation changes
Mermaid's major version; that is outside this bounded security-gate repair.

Sources: [DOMPurify 3.4.17](https://github.com/cure53/DOMPurify/releases/tag/3.4.17),
[Zod advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5). Existing dependency
licenses remain subject to the frontend/renderer license gates.

The first local production and diagram rehearsals could not start PostgreSQL
when Docker storage filled; renderer logs also reported ENOSPC. Previously
authorized unused build-cache cleanup reclaimed 4.312 GB. No application assertion
was loosened. The unchanged production rehearsal passed after cleanup; the diagram gate
was restarted against its own disposable project. Initial source-mounted OpenAPI comparison picked up an ignored
local 0.8.46 egg-info directory; checking the rebuilt image's own installed
0.9.11 package instead passed with DRF 3.18.3, no OpenAPI drift, and no broken
requirements. The Docker authorization gate passed 13 tests.

Fresh locked Docker frontend validation passed 127 files / 772 tests, API drift,
lint, types, production build and bundle budgets. Frontend license policy passed
620 package versions; renderer license policy passed 187. The renderer dependency
contract still verifies preview/export Mermaid alignment and Chromium 155.
Production-image rehearsal passed with the patched dependency set. The first
frontend invocation used existing host dependencies and was superseded by this
fresh locked Docker run; its partial output is not update evidence.

The isolated `make test-diagram-exports` gate passed after cleanup, including
document/diagram regressions and two explicit renderer-runtime checks for
deterministic bytes, sandboxing and cleanup. Two renderer-runtime tests are
intentionally skipped in its first non-runtime phase and executed in the
second phase. Hosted dependency review, image vulnerability scans and browser
journeys remain required before merge; no new published release is claimed.

## Hosted confirmation

Build [40049911922](https://github.com/hkrewson/TekDocs/actions/runs/40049911922),
CodeQL [40049911846](https://github.com/hkrewson/TekDocs/actions/runs/40049911846)
and performance diagnostics
[40049911842](https://github.com/hkrewson/TekDocs/actions/runs/40049911842)
passed for source `9814ab8adb46492f19f1316a157dc026f6990ab3`.
Build includes all PostgreSQL shards, runtime authorization, Chromium, live
Workspace and diagram journeys, coverage, and all four production image scans.
This supersedes the pending PR confirmation above. Release-only extended checks
and publication were correctly skipped; they will run on the versioned main push.
