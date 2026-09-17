# DNS record transfer between zones

Phase 3 (#80), required pre-1.0 under #60/#75. Version remains 0.8.46.

## Implemented boundary

A selected DNS record now offers **Move to another zone** inside the existing zone
drawer or full-page record view. The action searches the authorized DNS-zone
collection in bounded 25-row pages, excludes the current zone, and suggests a new
owner name by retaining the current relative label and replacing its zone suffix.
The owner remains editable before confirmation.

The transfer retains record type, value, TTL, priority, weight, port, linked IP
inventory record, description, entity identity and audit history. On success the
record leaves the source zone's child collection and can be opened from the
destination zone. Search, selection and owner-name drafts use the shared navigation
guard. Failed requests keep the draft visible and are not retried automatically.

## API and validation contract

Transfer is an isolated partial update containing exactly `zone_id`,
`expected_zone_id` and `owner_name`. Ordinary edits cannot change a zone, and a
transfer cannot mix in ordinary record fields. The service locks the record before
comparing its current zone, returns 409 for a stale or same-zone request, resolves
the destination inside the exact workspace, then applies all existing canonical
name, zone ownership, type, CNAME and IP-link rules. Successful transfer appends the
existing `dns_record.updated` audit action. No route, model, migration, permission or
dependency was added.

## Verification

Focused service coverage exercises missing compare state, mixed edits, same-zone,
stale, cross-workspace and invalid-owner requests plus a successful transfer that
retains all non-parent data. Component and API-client coverage verify the suggested
owner, exact request body, failure retention and navigation protection. Responsive
browser coverage exercises the searched move in the existing drawer. The isolated
live workspace journey creates two zones, moves the edited record, reloads it from
the destination and independently verifies ownership, retained values and its three
append-only audit events in PostgreSQL.

Final `make check` verification passes backend lint and types, migration and API
schema agreement, all 581 frontend tests in 116 files, coverage, the production build
and existing bundle budgets. The focused move passes in Chromium, Firefox and WebKit.
The isolated live workspace journey passes, and the complete
`make test-network-validation` PostgreSQL, stabilization and repeated frontend
workflow exits 0.

This completes the bounded DNS transfer checkpoint. Wider Phase 3 technician and
release acceptance remain open. No push, production deployment or version change is
part of this work.
