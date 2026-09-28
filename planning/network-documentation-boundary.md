# Pre-1.0 network documentation boundary

Decision corrected 2026-09-28. This supersedes the broader network-object
workspace described in the original responsive Phase 3 plan. TekDocs documents a
small set of useful network facts and may import them from authoritative systems.
It does not recreate NetBox, an IPAM, a DNS controller or a network-management
platform. Version remains 0.8.46.

## Supported workspace

Networks has exactly five primary views:

1. **Networks** — CIDRs and their directly useful addressing facts.
2. **Devices** — asset-backed network devices, primarily adopted from NetBox.
3. **DNS** — DNS records entered manually or observed from a supported DNS
   provider.
4. **Wireless** — wireless documentation; its final retained field set must be
   reviewed before destructive cleanup.
5. **NetBox** — connection/sync evidence, source identity, last observation and
   actionable conflicts.

VLANs, VRFs, racks, circuits and handoffs are not primary views. Interfaces, IP
addresses and MAC addresses are not workspace-wide inventory products. A legacy
URL for a removed view returns to Networks instead of exposing its old authoring
surface.

## Network record

The CIDR is the record identity and the main list value. A network may retain:

- canonical CIDR;
- optional VLAN ID as an integer attribute of the CIDR;
- derived subnet mask;
- derived broadcast address when the address family has one;
- optional DHCP server IP;
- a bounded list of explicit DNS server IPs;
- explicit IP assignments inside the CIDR;
- manual or provider source identity and observation time.

Subnet mask and broadcast are calculated from the canonical CIDR and are never
separate authored truth. An assigned IP stores its address and an optional asset
assignment. Users may assign it while viewing the network or while viewing the
asset; both actions edit the same record. An interface is not required. Address
validation ensures the IP is inside the CIDR and excludes reserved network or
broadcast addresses where applicable.

The current name, location, description, notes, gateway and custom assignable-range
fields are outside the newly agreed retained contract. They may be removed after
the migration proves that no allowed value depends on them. “DHCP server IP” is a
specific host address; it is distinct from an assignable range and from an IP row
whose status happens to be DHCP.

## Device projection and NetBox adoption

A network device is an asset with network-device classification. The Devices list
may show:

- device name;
- NetBox object ID;
- rack label;
- rack position;
- height in rack units;
- serial number;
- manufacturer, product and model derived from the NetBox device type;
- source and last-observed state needed to understand synchronization.

Rack is displayable placement data on the device. It is not a separately managed
TekDocs record. Device role/status and other NetBox fields are retained only if a
later explicit product decision adds them to this list.

On synchronization, a NetBox device should deterministically match or create the
manufacturer/product/model records, create the hardware asset when no confident
match exists, classify it as a network device, and attach its NetBox identity.
Routine unmatched devices are adopted automatically. Human review is reserved for
ambiguous matches, incompatible existing records and destructive changes. A new
workspace must not require operators to recreate NetBox inventory manually.

Provider-owned values update from later observations. Locally authored values that
are part of the supported contract require an explicit ownership rule before a
provider can overwrite them. NetBox references and observation digests are evidence,
not a second authoring surface.

## DNS and wireless

DNS is a list of DNS records. Manual entry remains possible, and later provider
adapters may observe records from systems such as Cloudflare, UniFi or Technitium.
Provider observations do not turn TekDocs into an authoritative DNS server and do
not write changes back to providers without a separate product and security review.

Wireless remains inside the approved navigation boundary. No current wireless
field is guaranteed merely because it already exists; the retained wireless
projection must be specified before its legacy model is reduced.

## UniFi observation boundary

UniFi Network is an optional read-only source for the existing five-view
workspace. It does not add a sixth Networks view and it does not make TekDocs a
controller. The supported provider projection is deliberately limited to:

- configured network details needed to describe a CIDR, VLAN ID, subnet mask,
  broadcast address, DHCP server and at most two DNS servers;
- adopted infrastructure identity needed to create or refresh a hardware Asset
  and show it in Devices;
- connected-client name, IP address and MAC address as time-bounded observations;
- Wi-Fi broadcast name, state, security and associated network for Wireless.

Connected clients are observations, not durable inventory merely because they
appeared on a network. A client may update an IP assignment only when TekDocs can
deterministically identify an existing Asset or an operator approves the match.
Unknown phones, guest devices and other transient clients never create Assets or
NetBox devices automatically.

Provider ownership remains explicit. NetBox owns durable inventory and placement
facts imported from NetBox. UniFi owns live connectivity and broadcast observations.
Locally authored values remain local unless a field has a documented provider
ownership rule. Source evidence stays in Integrations and on the affected record;
it is not another network-management surface.

Publishing an eligible UniFi-derived change to NetBox is a separate reviewed
operation. It requires a separately configured NetBox write credential, shows the
exact proposed create or update before execution, revalidates both source and
target immediately before writing, and records the result. There is no automatic
UniFi-to-NetBox feedback loop.

## Data reduction sequence

Existing data is preserved only long enough to extract the agreed values safely.
The pre-1.0 sequence is:

1. Remove VLAN, VRF, rack and circuit views and creation paths from Networks.
2. Add the final CIDR projection, including derived mask/broadcast, DHCP server,
   DNS server list and asset-address assignment from either parent.
3. Replace rack relationships with device placement values and make Devices an
   asset projection.
4. Make NetBox sync create/update supported asset, model, device and CIDR records
   automatically; retain only ambiguous cases for review.
5. Define the retained DNS-provider and wireless projections.
6. Add the bounded UniFi reader and prove that unsupported or transient values
   remain observations; then add deterministic projection into the retained views.
7. Add reviewed NetBox publication only after the separate write-credential,
   proposal, authorization and audit contract is implemented.
8. Backfill supported values and source evidence, verify counts and relationships,
   then remove the superseded APIs, models, permissions, preferences, tests and
   stored rows for VRFs, standalone VLANs, racks, interfaces, MAC addresses,
   circuits and handoffs.

Destructive migrations must first report what will be retained and deleted in a
fixture and production-image rehearsal. They must not keep hidden legacy tables
indefinitely merely because the old interface once exposed them.

## Acceptance

- Navigation contains only Networks, Devices, DNS, Wireless and NetBox at every
  supported width.
- A NetBox device can become a complete asset-backed device without prior manual
  catalog, asset, rack or network-device creation.
- A NetBox prefix can become a CIDR record with its VLAN ID and provider identity
  without prior VLAN or VRF creation.
- Network and asset views edit the same IP assignment.
- CIDR-derived mask and broadcast are stable for IPv4 and IPv6 semantics.
- Fresh-workspace sync, repeat sync, changed observations, ambiguous matches and
  provider failures are explicit and recoverable.
- UniFi sync reads only the documented sites, networks, adopted devices, connected
  clients and Wi-Fi broadcasts endpoints and retains only the bounded projection.
- Transient UniFi clients remain observations unless an asset match is deterministic
  or approved; no provider write occurs during synchronization.
- A NetBox publication cannot occur without a separately configured write
  credential and an explicit review of the current proposal.
- Removed routes and controls cannot create extraneous record types.
- Upgrade and recovery rehearsals prove the allowed values survive final cleanup.
