# Wireless parent assignment — Phase 3 #80

This bounded follow-up completes parent-network assignment for the parent Wireless
section and workspace Wireless register. Version stays 0.8.46 under #60/#75. Site
and VLAN editing remain separate work; no existing associations are inferred or
silently rewritten.

## User flow

Open an SSID, choose Change parent network, search by network name/CIDR, select a
result, and Save parent network. Use no parent network explicitly clears that link.
The section opens in the current record/drawer, with keyboard focus on its heading;
there is no additional drawer or modal picker. Ordinary wireless editing is hidden
while assignment is active, and assignment is unavailable while ordinary editing
is active. Read-only users do not receive either editing action.

The selected network remains visible while searching or paging. Search runs on the
full authorized network collection and resets its own page. Results use 25 summaries
per page and the existing deterministic name ordering. Native labeled select controls
keep the picker compact; selected values remain visible outside the dropdown. Search
and picker pages are transient form state, not saved collection preferences.

Cancel, drawer dismissal and route/tab changes use the shared dirty-form guard.
Failed/denied saves retain the selected ID and label, display the server error and
never automatically retry a mutation. Failed lookups allow retry; an empty result
never clears the selected parent. Choosing the existing parent is a no-op.

When a parent-scoped SSID moves away, selection clears and the original parent's
Wireless collection reloads. A generic record notice explains its departure. In the
workspace register the record remains open; a changed filter match is explained
inside the drawer where the notice is accessible. Closing returns to retained list
state. Reload confirms persisted associations through the selected detail endpoint.

## Contracts and verification

Uses existing NetworksClient.collection with q/page/page_size=25/ordering=name and
bounded summaries. Saving PATCHes only subnet_id through updateWireless; site_id,
vlan_id, SSID, security, status and other facts are deliberately omitted. Existing
Django scoped relationship validation and wireless serialization/row locks remain
authoritative, including VLAN/subnet consistency and foreign-workspace rejection.
No API endpoint/response contract, generated schema, migration, permission or
personal-preference model changes are needed.

Tests cover attach/move/remove, retained facts, foreign-parent rejection, bounded
search/paging, empty/failed lookup, failed save, cancellation, read-only actions,
parent departure and active workspace filters. Browser coverage includes the six
required widths and maintained engines, keyboard focus, touch/short screens, 200%
zoom and accessibility. The live journey attaches and detaches an SSID and refreshes
from Django/PostgreSQL. Executed results are recorded in progress.md.

Remaining Phase 3 work includes site/VLAN association editing and other network
object surfaces. Technician walkthroughs, release acceptance and existing pre-1.0
security/recovery/recurring-invoice obligations remain open. Local runtime rebuilding
is separate from production publication; retain all user and demo data.

Follow-up: site/VLAN assignment browser scenarios reproduced the previously intermittent
post-save dirty-guard symptom more consistently. The shared guard now registers and
unregisters with layout effects so visible editor state and navigation agree. See
wireless-site-vlan-assignment.md and progress.md for reproduction and verification.
