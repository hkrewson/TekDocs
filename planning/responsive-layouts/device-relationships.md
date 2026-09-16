# Device relationships within device records

Phase 3 (#80), required pre-1.0 under #60/#75. Version remains 0.8.46.

## Implemented boundary

Authorized device records now include a Relationships section beside Overview,
Placement, Interfaces and History. It uses `devices_section=relationships`, works in
the existing drawer and optional full-page record, and remains stable across refresh,
Back and Forward navigation. A direct relationship URL falls back to Overview when
the user cannot view relationships, and the unavailable section is omitted from both
desktop tabs and the mobile Sections selector.

The section loads only the selected device's authorized links. Users with create
permission can search network-device candidates in the exact workspace, choose an
eligible `Connected to`, `Depends on` or `Related to` link and add it. Users with
archive permission can remove an existing link. Incoming links remain visibly marked
as backlinks. The server's relationship permissions and validation remain
authoritative; network edit access alone does not expose these actions.

An unfinished relationship search, type or target selection participates in the
shared dirty/busy navigation guard. Section changes, drawer dismissal and browser
navigation therefore retain the draft until the user explicitly discards it. Failed
loads and writes remain visible and are never retried automatically. Existing
relationship endpoints, models, migrations and permissions are unchanged.

## Verification

Component coverage exercises direct relationship URLs, permission-controlled section
visibility, exact-workspace search/create, archive, failed loading and unfinished-draft
navigation. Browser coverage enters the section at all six maintained widths and
checks drawer fit. A touch journey creates a relationship, preserves an unfinished
search through guarded navigation, reloads the direct URL, archives the relationship
and runs an accessibility scan. The isolated live workspace journey creates a real
`Connected to` relationship and independently verifies the exact stored link and its
single creation audit event in PostgreSQL.

Executed gate results are recorded in [progress.md](progress.md). Hardware-binding
replacement, remaining network surfaces, technician walkthroughs and full Phase 3
and release acceptance remain open. No production publication or version change is
included.
