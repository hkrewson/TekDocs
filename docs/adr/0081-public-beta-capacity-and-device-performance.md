# ADR 0081: Public-beta capacity and constrained-device performance

Status: Accepted

Date: 2026-08-13

## Context

The early performance fixture protected authorization and query shape at 10,000 Entities, 2,500 block revisions, and small inventory pages. That was an effective regression tripwire, but it did not exercise the 1.0 reference shape of 100 clients, 100,000 addressable Entities, 250,000 immutable revisions, and 25,000 assets. The React shell also remained close to its original 500 KiB ceiling, while the optional Milkdown/Crepe editor was weighed but not exercised under constrained CPU and network conditions.

Performance work cannot bypass exact-Workspace policy, forced RLS, or field projection. Nor should a development-host timing be presented as a universal sizing promise.

## Decision

- A dedicated PostgreSQL capacity gate constructs at least 100 client Workspaces, 100,000 Entities, 250,000 revisions, and 25,000 assets. It measures warmed first, middle, and final asset pages, deep revision history, broad scoped entity search, fixed whole-request query ceilings, and eight simultaneous authorized reads.
- Ordinary warmed reads retain the existing 500 ms local p95 tripwire. The controlled eight-request burst has a separate two-second ceiling so resource contention is visible without pretending it is an ordinary single-request result.
- The fixture uses the same API, central-policy, exact-Workspace, pagination, serializer, and PostgreSQL paths as production. It does not introduce an unscoped cache or an aggregate MSP surface.
- Feature surfaces that are not part of initial navigation load through route chunks. The executable shell ceiling is tightened from 500 KiB to 400 KiB; the editor remains a separately loaded route dependency with its 1,200 KiB ceiling. Shell and editor stylesheets also receive explicit ceilings.
- CodeMirror is disabled in the WYSIWYG configuration because TekDocs does not require its executable syntax editor to preserve fenced Markdown. Canonical fenced code remains supported in Markdown and server rendering.
- A production-build Chromium rehearsal uses deterministic CPU and network throttling for constrained desktop and mobile viewports. It proves the editor chunk is absent before a document opens, records decoded JavaScript and ready times, and blocks gross regressions. This is a repeatable proxy, not physical-device or field telemetry.
- The capacity test is a named gate rather than part of the fastest edit loop. It remains part of release evidence and must run on the documented reference host after performance-sensitive changes.

## Consequences

The full dataset now provides an executable capacity boundary and the initial shell has materially more headroom. The visual editor is still large; its current upstream packaging emits optional syntax assets and does not become small merely because CodeMirror is disabled at runtime. Replacing Crepe or rewriting the editor solely to improve a synthetic bundle number is not justified while constrained-device interaction remains inside the explicit boundary. Final release-candidate measurement remains recurring work.

These results do not establish maximum tenant size, sustained throughput, a concurrent-user SLA, or hosted multi-tenant capacity. Operators must size and observe their own installation.
