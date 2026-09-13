# Workspace Wireless register — Phase 3 #80

This extends the parent Wireless checkpoint under #60/#75. Version stays 0.8.46.
Networks → Wireless lists all authorized SSIDs in the current MSP/client workspace,
including records without a parent network. Existing parent-specific lists remain
inside their network record; both use NetworkChildCollection and the same editor.

## Interaction and URLs

Names open the complete record in the shared overlay drawer, with Overview and
History sections. Outside click/Escape closes it; mobile has a Back link. The list
stays behind the locked overlay. An optional full-page link supports separate tabs
and bookmarks. Unavailable records retain a return path. Dirty forms guard section,
record, view and page navigation; failed saves keep values and never retry mutations.

The owning /networks route (including organization routes) uses view=wireless.
Collection state is ssid_q, ssid_status, ssid_association, ssid_order, ssid_page and
ssid_size. Selected record is ssid, with ssid_section=overview|history and
ssid_full=true for the optional page. Creation uses ssid=new. History uses the shared
history_page parameter and fetches only when selected. Transient browser state
childListY restores scroll; row/heading focus returns after dismissal. Switching
Network views clears record selection while retaining each collection's query state.

Default columns: identity, network CIDR, status, security. Purpose is also selectable.
The shared filter menu offers status and assigned/unassigned network association,
with removable summaries. Search includes SSID and parent CIDR across the entire
workspace; pages remain 25/50/100. There is no cross-page bulk selection.

## API, ownership and compatibility

Existing bounded wireless endpoints gain association=assigned|unassigned and
ordering=network|-network. Search also checks parent CIDR. Parent-scoped subnet_id
can combine with association; contradictory filters yield an empty collection.
Workspace authorization remains applied first, deterministic ID ties remain, and
legacy calls retain their default response and ordering. OpenAPI/types are updated.

Personal feature wireless-register has networks.view permission and the existing
installation/user ownership model. It stores columns/page size, independently from
network-wireless preferences. No new data model, migration or RLS classification.
Defaults work when preferences fail. Existing networks.edit authorization controls
mutations; UI permissions never replace server checks.

Creating from the register leaves subnet_id null. Editing deliberately omits parent,
site and VLAN IDs, preserving current associations. Association editing/reassignment
is still open, as are other network object surfaces and Phase 3 acceptance. This
checkpoint does not close technician, production/release, security, recovery or
recurring-invoice obligations. See progress.md for executed verification evidence.
