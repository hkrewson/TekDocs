# Reminders agenda and activity event stream

Phase 7 begins with two operational shell surfaces that previously used an
always-expanded form and a wide audit table. This checkpoint replaces those
layouts while preserving the existing permission, workspace and audit rules.

## Delivered behavior

### Reminders

- `/deadlines` and organization-scoped deadline routes use a compact agenda with
  bounded pages of 25, 50 or 100 records.
- Search covers reminder titles and source names across the authorized
  collection. Domain and deterministic due-date/title ordering use URL state.
- The creation form opens only when requested through `new=1`. Its source picker
  remains bounded, failed writes retain entered values, and the shared navigation
  guard protects drafts when canceling or leaving.
- Active filters have a compact summary, the existing calendar export remains
  available, and retry/empty/loading states stay inside the single page scroll.
- The API adds an explicit `paginated=true` response with count, page, page size
  and continuation state. Existing callers without that flag keep the legacy
  reminder array instead of receiving a silently changed contract.

### Activity

- `/activity` and organization-scoped activity routes use an event stream that
  prioritizes action, record, time and actor instead of a five-column table.
- Search, date range, page and page size are URL-addressable and query the full
  authorized collection. Request IDs are visually shortened while retaining the
  complete value as accessible title text.
- Results use the existing bounded activity response and keep loading, failure,
  retry and empty states in the main scroll area.

## Compatibility and security

The reminder write model, workspace resolution, permission checks, entity scope,
calendar format and audit-event creation are unchanged. The new reminder query
serializer rejects unsupported values, limits page size to the shared choices and
orders equal values by stable entity identity. The collection response does not
include source detail, histories or relationships.

There is no database migration. OpenAPI and generated browser types describe the
additive paginated response while retaining the legacy array. Version remains
0.8.46.

## Verification

Required coverage includes 31-record API paging and off-page search, legacy
response compatibility, component filter and creation behavior, dirty-draft
retention, URL restoration, keyboard-accessible controls, axe checks and no page
overflow at 320, 390, 768, 1024, 1280 and 1440 CSS pixels. The maintained-browser
matrix runs the responsive scenarios in Chromium, Firefox and WebKit.

The live workspace journey creates a reminder for a real PostgreSQL-backed
document, reloads the agenda, independently reads the bounded API result, and
finds the resulting audit event through the activity surface after refresh.

This checkpoint does not complete Phase 7. Search, overview, notifications,
recycle bin, metadata, account/access/setup/help/status and client-portal surfaces
remain in the phase inventory.
