# DNS register and records within zone drawers

Phase 3 (#80), required pre-1.0 under #60/#75. Version remains 0.8.46.
Status: DNS implementation checkpoint verified; broader Phase 3 and release acceptance remain open.

## Implementation boundary

Networks now includes DNS. The zone register uses name and record count, server
search/sorting, 25/50/100-row pages, personal column choices/reset, and full record
drawers. Overview, Records and History have direct URL state; the shared full-page
link, mobile Sections menu, backdrop/Escape dismissal and return focus apply.
The old orphaned NetworkServices stacked DNS/wireless implementation is removed.
Wireless continues through its already migrated register.

Records live inside their owning zone's drawer, without a second overlay. Their
collection has owner, type, value and TTL columns, a type filter, bounded search
and paging. Long list values are shortened visually; selected detail exposes the
entire value. Overview also exposes the complete zone name for read-only members
when a long name is shortened in the drawer heading. Descriptions are omitted in explicit summary responses and fetched
for the selected record. Opening the zone never fetches every DNS record or
unrelated wireless/VLAN/subnet/IP collection.

Zone and record creation/editing preserve existing DNS rules, including canonical
names, zone ownership, record-type fields, CNAME restrictions and IP matching.
Record creation fixes the parent zone. Ordinary record PATCH omits zone identity;
there is no new move-between-zones action. Failed writes retain entered values,
with no automatic retry. Dirty and busy forms use the shared navigation guard.
The zone Overview discloses that edits do not publish live DNS. Renaming a zone
with records remains prohibited by the server and explained in the form.

A/AAAA forms offer a paginated, searchable IP inventory picker. Its current page
shows both address families, disabling incompatible choices, with full authorized
page counts; selected records outside the page remain linked. Removing the link
changes the draft only and preserves the entered DNS value. No IP records are
created, moved, or deleted by this picker. The existing server matching and exact
workspace checks remain authoritative.

## URL and API contracts

- `view=dns`, `dns=<zone-id|new>`, `dns_full=true`, `dns_section=overview|records|history`.
- `dns_record=<record-id|new>` selects a child within Records. Parent mismatch is
  rejected even if the record is otherwise authorized. Changing zones clears child
  selection; returning preserves collection query/page state.
- Zone collection state uses `dns_q`, `dns_page`, `dns_size`, `dns_order`.
  Records use `dns_record_q`, `dns_record_page`, `dns_record_size`,
  `dns_record_order`, `dns_record_association`; association maps to type.
- `dns_record_view=history` opens the selected record's history on demand. It is a
  focused view inside the same zone drawer, with Back to record details, rather
  than another tab bar or overlay. `dns_record_history_page` preserves its page
  separately from the zone's existing `history_page`. Switching records clears
  child-history state; moving between details/history within one record retains it.
  Refresh, full-page links and browser navigation preserve the selected history.
  Dirty/busy navigation protection applies before opening history.
- Selected record headings take keyboard focus. History denial or failed reads
  retain the record-details return link; missing/mismatched records do not fetch
  history. DNS audit actions use readable created/updated labels.
- Existing DNS list endpoints gain explicit `q`, `ordering`, `summary`; records
  additionally support `zone_id` and `record_type`. Search includes descriptions
  and record values. Ordering uses entity IDs to break ties. Invalid parameters
  are rejected; an unavailable parent is denied.
- Existing no-query list behavior retains its default 50-row pages, full
  descriptions and prior ordering. The UI explicitly requests 25-row summaries.
- `dns-zones` and `dns-records` reuse the personal preferences model, installation/
  user ownership and network permission filtering. No schema migration, domain
  rule change, new permission or application dependency.
- OpenAPI and generated TypeScript are regenerated using pinned dependencies.

## Verification and remaining work

Frontend component coverage includes lazy/scoped loading, parent mismatch, read-only
access, failed-edit/history-navigation guards, namespaced history paging, history denial, fixed-parent SRV creation with zero-valued
priority/weight, new-form return protection, paged IP choices and wrong-family
selection prevention. Browser coverage includes all six widths across Chromium,
Firefox and WebKit, refresh, full-page/Back navigation, return focus, long content,
axe checks, denied/unavailable/failed/empty states, touch/short-height and 200% zoom.

Added PostgreSQL regressions cover 31 records, off-page search, page boundaries,
summary/legacy compatibility, deterministic ordering, filters, invalid queries,
sibling scope and preferences/reset. The isolated live workspace rehearsal now
creates a DNS zone and TXT record through the browser, updates TTL, refreshes, and
reads its created/updated history and returns to the record list. Independent
PostgreSQL assertions verify exact workspace/tenant, TXT value, TTL 600, absence
of an unintended IP link, and the two expected audit events. These database and live checks now pass in Docker, including the full real-browser
journey and independent retained-data assertions.

Zone transfers and broader Phase 3 technician/release acceptance remain follow-ups. No production publication or version change.
See progress.md for executed evidence, reproduced failures and their fixes.


History follow-up: `RecordActivity` accepts an optional page-parameter name while
existing callers keep `history_page` unchanged. This presentation-only addition
uses the existing authorized activity API and adds no server permission or model.
Reproduced missing child heading focus before the change; component and browser
checks now cover it, including the retained focus after history pagination.


Final checkpoint verification: `make check` passes with 547 frontend tests and
build budgets; `make test-network-validation` passes; all 15 network-service and
12 collection-preference PostgreSQL cases pass. All 36 DNS browser cases pass
across Chromium, Firefox and WebKit, along with 13 focused component cases.
`make test-e2e-live` passes through the real browser, Django and PostgreSQL.
The live run uncovered and verified a fix for DNS updates locking an optional IP
join: the service now explicitly locks the record and identity rows. The new
regression checks retained fields, parent/workspace and the expected audit pair.

Remaining: DNS zone transfers, circuits/handoffs, other Phase 3 objects and
technician/production-image/release acceptance. No production publication or
version change is included in this checkpoint.
