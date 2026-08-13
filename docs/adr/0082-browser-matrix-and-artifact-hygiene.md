# ADR 0082: Browser matrix and value-free artifact boundary

Status: Accepted

Date: 2026-08-13

## Context

Chromium-only pull-request coverage is fast and useful, but it cannot establish that routing, forms, lazy loading, focus, and responsive navigation behave under Firefox and WebKit. Running every journey against every device on every change would make the edit loop unnecessarily slow. Playwright's usual failure traces and screenshots are also unsafe defaults for TekDocs: authentication, MFA, invitations, recovery, API tokens, private documents, and client records can exist in browser memory or the DOM when a test fails.

## Decision

- Pull requests run the complete desktop Chromium suite. Scheduled, manually dispatched, and release evidence adds complete desktop Firefox and WebKit suites.
- Two narrow responsive projects run a dedicated small-screen contract under Pixel-class Chromium and iPhone-class WebKit. They cover reflow, absence of page-level horizontal overflow, mobile navigation, keyboard/touch operation, and WCAG 2.2-tagged automated checks. They supplement rather than replace manual physical-device and assistive-technology review.
- Every project uses the same isolated production-asset Compose rehearsal and digest-pinned Playwright image. Host-only browser execution cannot close the slice.
- Trace, screenshot, and video capture are off by default. The CI boundary does not upload HTML reports, DOM snapshots, attachments, storage state, request/response bodies, console logs, or raw test output.
- A custom reporter emits only schema version, overall status, project, test title, status, duration, and retry. A separate gate requires one ordinary JSON file, rejects symlinks and files over one MiB, validates the summary shape, and rejects representative secret markers.
- Reporter output lands in a local quarantine directory. The rehearsal validates the exact file before atomically promoting it into the only directory CI may upload; a malformed or secret-bearing report therefore cannot become an artifact even when the browser suite fails.
- Hosted artifacts retain only the promoted project summary for seven days. Adding another browser artifact type requires an explicit classification and threat review, synthetic-only fixtures, proven redaction, least-privilege readers, and bounded retention.

## Consequences

Failures retain enough metadata to identify the project and test but deliberately sacrifice rich remote debugging evidence. Reproduction occurs in the same isolated local rehearsal, where an operator may make an explicit short-lived debugging choice without turning that capture into a checked-in or hosted artifact. The matrix improves engine and responsive confidence but is not physical-device, screen-reader, hosted-workflow, or external certification evidence.
