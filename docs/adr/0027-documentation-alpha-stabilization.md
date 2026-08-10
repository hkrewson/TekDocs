# ADR 0027: Documentation-alpha stabilization boundary

- Status: Accepted for `0.2.9`
- Date: 2026-08-09

## Decision

Revision history is a validated, permission-scoped paginated API. The default page is 50 records, callers may request at most 100, the response reports the complete authorized count and whether an older page exists, and the UI never substitutes a fixed truncation for navigation. The stabilization fixture retains 2,500 revisions amid the existing 100-organization/10,000-entity dataset and applies both query-count and p95 latency tripwires. This is an alpha regression boundary, not the final 250,000-revision capacity claim.

The Milkdown/Crepe editor remains a route-lazy optional dependency. Its CSS and optional code-syntax assets load with the editor instead of the application shell. A build gate caps ordinary JavaScript chunks at 500 KiB and the current editor chunk at 1,200 KiB minified. A manual vendor split was tested and rejected because it duplicated Crepe and CodeMirror internals, increasing delivered bytes. The residual editor size remains an explicit risk for representative-device work in `0.8.5`.

ADR 0019 and its fixed round-trip fixture remain the Markdown source of truth. A blocking UI test proves internally hosted Formatting help names the supported syntax and the unsafe exclusions; renderer, sanitizer, editor, and browser accessibility tests remain separate required layers. TekDocs will not create a repository `docs/` user manual as a substitute for the intended public GitHub Wiki. Wiki publication and contextual links remain `0.8.8` work after external publication is authorized.

Recovery evidence has two distinct rehearsals. One upgrades retained `0.2.8` documentation, history, attachment bytes, signed publication, and PDF into `0.2.9`. The other independently captures PostgreSQL and the media volume, restores them into clean volumes, and uses separately retained deployment keys to verify the same data and artifacts. These are disposable evidence scripts; they are not supported encrypted backup tooling, scheduling, remote retention, destructive-operation safeguards, or key-loss recovery. Those obligations remain with `TD-RISK-006` in `0.8.1` and `0.9.3`.

## Consequences

- Large histories are navigable and bounded without changing immutable revision identity or authorization.
- The ordinary shell stays independent of editor presentation and syntax assets, while the editor's remaining size is measurable and cannot silently grow.
- Recovery claims include both database rows and private file artifacts, but operators must not mistake an alpha rehearsal for a supported production backup product.
- No new documentation domain feature is introduced in this slice.
