# Notifications and recovery workspaces

This Phase 7 checkpoint makes the shell notification surfaces and both recycle-bin
scopes usable at realistic volume and on small screens. It keeps version 0.8.46
and preserves notification authorization, retention, archive semantics and recent
MFA requirements.

## Notification inbox

- The shell bell opens one overlay with a fixed header and one scrolling body.
  It fills the screen below 768 CSS pixels and locks background scrolling at all
  widths. Outside clicks and Escape dismiss it; mobile also exposes an explicit
  close control.
- Notification history stays cursor based and loads only when the inbox opens.
  Loading, empty, failure and older-page failure states remain distinct.
- Read-state failures are visible without hiding the inbox or pretending the
  mutation succeeded. Record targets keep their existing direct navigation.
- Email preferences remain a focused subview. Unsaved changes are protected when
  closing, pressing Escape, clicking outside or returning to notifications, with
  Keep editing and Discard changes choices. Failed saves preserve every value.
- All migrated labels and states use the application language catalog. The same
  component and interaction contract apply in the MSP shell and client portal.

## Email delivery

The staff-only delivery route is a compact operational exception feed. Recipient,
client, event identifier, delivery status, attempts and next-attempt time remain
available without a seven-column table or horizontal page scrolling. The status
condition is URL-addressed, visible outside the shared filter menu and removable.
Initial read failures can be retried without losing the selected status.

Dead-letter delivery remains the only inline mutation. It still requires an
explicit reason, preserves that reason after a denied or failed request, and never
retries automatically. The page continues to omit message bodies and recipient
email addresses. Older history retains the opaque cursor contract.

## Recycle bin

- MSP and organization recovery collections share URL-addressed search, record
  type, page and page size. They default to 25 and offer 25, 50 or 100.
- The compact recovery list prioritizes record identity, type, archived time,
  cascade size and restore eligibility. The former five-column scrolling table is
  removed.
- Search and type conditions are visible and removable. Collection reads have
  explicit loading, empty, filtered-empty, denied/failure and retry states.
- Restore remains a focused confirmation that explains cascade impact. Server
  authorization, recent MFA, parent dependency checks and workspace isolation
  remain authoritative. Failed restores retain the selected record and never
  retry automatically.
- The API change is additive: the maximum page size increases from 50 to 100
  while the existing default of 25 and smaller explicit sizes remain compatible.

## Verification

Coverage includes unread/read failures, cursor history, preferences loading and
saving, unsaved preference dismissal, status-filter restoration, dead-letter
retry, recovery paging/search/type state, permission-disabled restores, cascade
confirmation, failed reads and successful restoration. The maintained browser
matrix exercises 320, 390, 768, 1024, 1280 and 1440 CSS pixels across Chromium,
Firefox and WebKit, including mobile overlay bounds, background locking,
accessibility and horizontal overflow. The live-stack journey archives and
restores a real organization site through Django and PostgreSQL and exercises
real notification preferences and delivery history.

This checkpoint does not complete Phase 7. Metadata, account/access/setup/help,
system status and the broader client portal remain open.

