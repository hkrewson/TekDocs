# VLAN and VRF registers — Phase 3 #80

This bounded checkpoint adds VLAN and VRF browsing/editing to Networks under #60/#75,
remaining pre-1.0 at 0.8.46. Related subnet navigation, wireless site/VLAN association
editing and other network surfaces remain separate follow-up work.

## Layout and navigation

Networks → VLANs / VRFs uses the shared bounded collection and complete-record
overlay drawer. Defaults are Name + VLAN ID or Name + Route distinguisher. Columns
retain curated order, identity is mandatory, reset restores defaults, and page sizes
are 25/50/100. There is no bulk action or artificial status filter for these records.

Names open the drawer, with Overview and History. Full-page links, record/tab direct
URLs, refresh and browser Back/Forward retain collection context. Below 768px the
shared Sections menu replaces desktop section links. Drawer dismissal is outside
click/Escape, with Back on mobile. Editing is one Overview form with Save/Cancel and
the shared dirty navigation guard. Failed/denied requests preserve values and never
retry mutations automatically. History fetches only when selected. Missing optional
route distinguishers and descriptions remain visible as missing information.

For kind=vlans|vrfs, the owning network route uses view=kind. Collection state is
{kind}_q, {kind}_order, {kind}_page, {kind}_size; selected ID is {kind}, with
{kind}_section=overview|history and {kind}_full=true for full-page display. New records
use {kind}=new. Browser state restores transient scroll/focus; direct links without
list history return to their owning collection. Changing Network views clears record
selection and preserves independent collection queries. Existing network/Wireless
routes stay intact. The unused legacy NetworkAddressing component is not mounted by
any supported route; no competing legacy VLAN/VRF layout is shown.

## API and persistence

Existing bounded VLAN/VRF collection APIs add q, ordering and summary. Search covers
name/description and route distinguisher, or an exact numeric VLAN ID. Supported
ordering: name/-name and vlan_id/-vlan_id or route_distinguisher/-route_distinguisher,
with deterministic entity-ID ties. Summary=true omits description. Calls without new
parameters retain their previous page defaults, ordering and full record fields;
no legacy results are silently truncated. Strict invalid-query rejection remains.
OpenAPI and generated types explicitly describe the additions and summary omission.

Detail/create/update endpoints and domain validation remain unchanged. Lists fetch
bounded summaries; only selected detail/history is loaded. Frontend shared collection
records can now omit subnet_id, while parent-scoped Address/Wireless validation stays
in place. Collection filter menus are omitted when a record kind has no filter axes.

Personal features network-vlans and network-vrfs use existing installation/user
preferences and networks.view permission. No new model, migration or RLS boundary.
All exposed columns require that same permission; no sensitive/restricted columns
are added. Existing networks.edit policy authorizes every mutation on the server.

## Verification and remaining work

API fixtures cover 31 records, off-page IDs, numeric/reverse sorting, legacy/summary
compatibility, invalid parameters, sibling-workspace denial and preference save/reset.
Component/browser checks cover drawer/page navigation, focus, read-only/unavailable
records, failed/dirty editing, column persistence/reset, collection retry/empty results,
six widths, touch/short screens, 200% zoom and accessibility. Live workflow creates,
edits and refreshes both kinds through Django/PostgreSQL. See progress.md for results.

This does not close related subnet navigation, remaining network records, technician
walkthroughs, release acceptance or other security/recovery/recurring-invoice
obligations. Preserve all user/demo data. Local rebuild and Wiki edits do not publish
a production release or change the version.
