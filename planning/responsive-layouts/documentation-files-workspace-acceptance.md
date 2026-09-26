# Documentation and Files workspace acceptance

Phase 5/8 (#60), required pre-1.0 under #75. Version remains 0.8.46.

## Accepted automated boundary

Documentation and Files now have a tested cross-surface journey in MSP and
organization workspaces. A document link in the bounded Files register opens the
focused reader at its direct route. Browser Back returns to the same Files URL,
restores the full-collection search value, and shows the same off-page file. The
organization journey keeps both the file collection and selected document inside
the exact client path.

The Files matrix exercises this journey at 320, 390, 768, 1024, 1280, and 1440
CSS pixels in Chromium, Firefox, and WebKit. Explicit 390- and 1280-pixel client
checks verify the organization collection endpoint and organization document URL.
All 24 cases pass with the existing pagination, long-filename, accessibility,
personal-column, and page-overflow assertions.

This cross-surface evidence complements the existing Documentation matrices for
the focused reader/editor, templates, reusable blocks, ownership and review,
publication and export, managed primary files and attachments, draft protection,
health and link search, revisions, and retained publication history. Those tests
already cover the six required widths and the applicable denied, failed, stale,
dirty, retry, Back/Forward, refresh, touch, keyboard, and PDF states.

## Remaining work

The MSP and organization Documentation and Files routes remain `in_progress`
until technician and assistive-technology walkthroughs and final recovery/release
approval are recorded. Production-image refresh handling is already covered by
[production-route-acceptance.md](production-route-acceptance.md). This checkpoint
does not change the API, schema, migration, permissions, document authority,
domain data, deployment state, or version.
