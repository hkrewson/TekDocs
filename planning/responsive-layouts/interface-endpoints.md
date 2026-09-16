# Interface IP and MAC records and assignment

Phase 3 (#80), required pre-1.0 under #60/#75. Version remains 0.8.46.

## Implemented boundary

A selected interface has Interface details, IP addresses and MAC addresses views.
Each endpoint collection replaces the current child content inside the device drawer;
there is no nested overlay. The IP collection has address/status/DNS columns and
status filters; the MAC collection uses a compact address column. Both support
server search, 25/50/100 pages, personal columns/reset and selected detail on demand.
IP details retain the network CIDR. Ordinary editing preserves subnet, interface and
hardware identity by sending only editable record fields. Add IP address and Add MAC
address open focused create forms already bound to the current interface. IP creation
uses a bounded, searchable subnet choice; assignment of an existing record remains a
separate explicit path. Successful creation opens the saved detail in place.

Assign existing IP/MAC address opens a bounded search of records that have neither
interface nor hardware assignment. A selected choice remains explicit when search
or page changes. Confirm assignment submits a distinct binding operation. Remove
from interface shows a focused confirmation explaining that the record and history
are retained; confirmation clears the binding and returns to the parent list.
Move to another interface opens a separate bounded picker that searches interface
and device names across the exact workspace. The selected destination stays visible
when search or page changes. Confirming moves the record, returns to the original
interface's endpoint list and leaves the record available under the destination.
Failures preserve drafts/choices and do not automatically retry uncertain mutations.
Dirty/busy protection covers navigation, closing and changing the parent section.

URLs use `interface_view=details|ip|mac` and `interface_ip=<id|new>` or
`interface_mac=<id|new>`. Each collection keeps its own query/page/order/size/status
parameters. Returning to its list restores focus; refresh/full-page/Back preserve
context. Changing interfaces/devices clears descendant selection. Details that do
not belong to the current interface remain unavailable, even if otherwise authorized.

## Assignment and compatibility contract

Existing IP and MAC collections accept `interface_id` or `unassigned=true`; both
together are invalid. Parent IDs must exist within the exact workspace. Unassigned
means neither an interface nor a hardware asset, never a permission-hidden binding.
MAC collections gain address/description search, deterministic address ordering and
optional summaries. Legacy default page size/full detail behavior remains; the UI
requests bounded summaries explicitly. Subnet collections also accept bounded
display-name/CIDR/description search, stable name/CIDR ordering and summary responses
for the create picker. OpenAPI and generated types are aligned.

PATCH accepts `interface_id` with required `expected_interface_id`. These two fields
must be the entire assignment request; they cannot be mixed with ordinary fields,
subnet changes or hardware identity. Attach expects null; detach expects the current
interface's entity ID. The existing record transaction checks the expected value
under a row lock. A stale value, same-interface destination or already-bound candidate
returns 409 without changing the record or adding an update audit. An interface-to-
interface transfer resolves the destination inside the locked transaction and requires
the same exact workspace. It never replaces hardware bindings. Existing network-edit
policy and exact workspace services authorize writes; existing hardware-edit policy
stays unchanged.

Create APIs accept an optional `interface_id` and resolve it inside the same database
transaction as the new IP or MAC record. Interface and hardware bindings are mutually
exclusive. The interface must belong to the exact workspace and requires network-edit
permission; supplying a hardware asset continues to require hardware-edit permission.
Failed creates leave the draft intact and never retry automatically.

Preferences use `interface-ip-addresses` and `interface-mac-addresses`, reusing the
existing installation/user ownership and RLS. No new route, model, migration,
permission grant or dependency. Existing address uniqueness, canonical format and
subnet rules remain authoritative.

## Verification and follow-up

API tests cover 31 unassigned candidates, off-page search, interface/device-name
search, parent filters, sibling workspace denial, invalid/mixed payloads, ordinary
edits preserving assignment, successful transfer, same-interface and stale conflicts,
protected hardware bindings, network-edit denial and audit counts. Concurrent IP/MAC
claims must produce exactly one winner and one conflict.
Component/browser checks cover one drawer, all six widths, long content, paging,
selected details, direct/full-page navigation, focus, touch/short height/200% zoom,
assignment selection, failed writes, confirmations and permission/parent failures.

The live rehearsal creates two interfaces, creates IP and MAC records on the first,
edits their descriptions, moves the IP to the second and removes the MAC assignment.
Independent PostgreSQL assertions verify the transferred IP binding, retained MAC
record/removal and audit history.
Executed results and reproduced failures are recorded in progress.md.

Workspace-wide MAC browsing, device relationships/hardware rebinding, remaining
network surfaces, technician sign-off and full Phase 3/release acceptance remain
open. Conflict-safe interface-to-device moves are recorded in
[device-interfaces.md](device-interfaces.md). IP creation in a subnet and asset MAC creation remain
available through their existing parent records.
No production publication or version change is included. The separate Wiki checkout's
previously recorded missing-page limitation is unchanged.
