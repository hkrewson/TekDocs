# Help and system status

This Phase 7 checkpoint gives every authenticated shell route a responsive,
route-specific help reader and turns System Status into a compact operational
summary. It keeps version 0.8.46 and does not broaden diagnostic data or
authorization.

## Contextual help

- The top-bar Help action resolves the current route to a maintained Wiki topic.
  It does not fetch or embed remote Wiki content in the application.
- Help opens as a right-aligned overlay on larger screens and fills the viewport
  below 768 CSS pixels. The header stays fixed while the body owns the overlay's
  only scroll region.
- Opening the reader moves focus to its heading and locks background scrolling.
  Escape, an outside click, or the explicit mobile close action dismisses it and
  returns focus to Help.
- Unpublished guides retain an explicit local status. When Wiki publication is
  enabled, the full guide remains a normal external link that supports opening in
  another tab.
- All controls and application-owned states use the language catalog. Topic names
  and summaries remain part of the reviewed route-to-help registry.

## System status

- The authorized page leads with TekDocs, database, and diagram-renderer health
  in three compact rows. Version, renderer capacity, queue depth, and last check
  remain available without an expansive definition grid.
- Degraded health remains prominent while the latest diagnostics stay visible.
  Initial and refresh failures have an explicit retry and never clear previously
  loaded service details.
- Recent renderer failures use a compact exception list instead of a table. Long
  service versions and error identifiers wrap without creating horizontal page
  scrolling.
- The existing diagnostic boundary remains authoritative: no documents, files,
  diagram source, rendered output, recipients, or secrets are returned. Existing
  `system_diagnostics.view` authorization and backend bounds are unchanged.

## Verification

Coverage includes route-topic resolution, local unpublished-guide state, opening,
Escape and explicit close behavior, focus restoration, background locking,
loading, unavailable, retry, ready and degraded diagnostics, queue capacity,
long identifiers and empty/recent failures. The maintained browser matrix covers
320, 390, 768, 1024, 1280 and 1440 CSS pixels across Chromium, Firefox and
WebKit, including accessibility and horizontal overflow. The live-stack journey
opens the value-minimized authorized endpoint and contextual help through the
real Django/PostgreSQL application.

This checkpoint does not complete Phase 7. Metadata, account/access/setup and the
broader client portal remain open.
