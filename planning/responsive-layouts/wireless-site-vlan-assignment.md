# Wireless site and VLAN assignment — Phase 3 #80

This pre-1.0 0.8.46 checkpoint adds focused Change site and Change VLAN actions to
wireless records in the workspace register and parent-network section. Only one
editor (ordinary facts, parent, site or VLAN) is active at once. No nested drawer or
desktop Close button is introduced. Existing outside-click/Escape and mobile Back
behavior remains, guarded while values are dirty or a request is outstanding.

## Editing and lookup contract

A focused assignment editor retains the current identity and label, including an
unavailable-current-assignment fallback. Search/paging does not clear the selection.
Explicit Use no site / Use no VLAN removes an association. Failed requests retain
values, show an error, and never retry a mutation automatically. Save sends only
`site_id` or `vlan_id`; other wireless settings and associations remain authoritative
on the server. Current networks.edit permission gates actions and every mutation.

New `/networks/assignment-choices` endpoints exist for MSP and organization workspaces.
They accept kind=site|vlan, q and bounded paging (default 25, maximum 100). Results
contain entity id, name, site code/VLAN number as identifier, collection metadata and
can_manage. Search covers names, site codes and exact numeric VLAN IDs. Ordering is
name then entity ID. No addresses, histories or unrelated choices are downloaded.
The existing networks.view policy for network choices is reused in the exact workspace;
existing full choice and VLAN APIs are unchanged. This is a new explicitly paginated
interface, not a silent truncation of legacy responses. No model/migration/RLS-policy
change or dependency is required. OpenAPI and generated types describe the new API.

## Reproduced navigation issue

The new immediate-save/remove/Escape browser scenarios reproduced stale dirty
confirmation after the editor disappeared, including Chromium site/VLAN cases.
The shared guard registered and cleaned up in a passive effect, leaving a window
where visible controls and registered state disagreed. Registration/cleanup now use
a layout effect so the guard agrees with committed UI before the next interaction.
The unchanged regression assertions require zero dialogs immediately after successful
save and Escape. Existing parent-assignment, asset dirty navigation and other record
flows are included in verification. See progress.md for executed results; do not
interpret this checkpoint as closing all remaining navigation acceptance.

## Remaining work

Devices, racks, interfaces, DNS, circuits and other network record surfaces, technician
walkthroughs and final Phase 3 acceptance remain open. Current assignment lookup
uses 25-row pages and local editor search; it is not a personal saved collection view.
Production publication and version changes remain separate steps. Local rebuild must
preserve user/demo data and volumes.
