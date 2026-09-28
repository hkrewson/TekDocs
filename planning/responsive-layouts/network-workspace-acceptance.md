# Networks workspace acceptance

Phase 3/8 (#80/#60), required pre-1.0 under #75. Version remains 0.8.46.
The product boundary is [the 2026-09-28 network documentation decision](../network-documentation-boundary.md).

## Supported navigation

The Networks entry point has five views: Networks, Devices, DNS, Wireless and
NetBox. At 768 CSS pixels and above they are direct links. Below 768 pixels they
become one labeled selector. Each view retains its direct URL, browser navigation
and MSP or organization workspace. Legacy `view=vlans`, `view=vrfs`,
`view=racks` and `view=circuits` URLs resolve to the CIDR collection and expose no
creation control for the removed record type.

`network-workspace-acceptance.spec.ts` traverses all five views at 320, 390, 768,
1024, 1280 and 1440 CSS pixels, a short 520-pixel viewport, and the 640-CSS-pixel
viewport produced by 200% zoom on a 1280-pixel display. MSP and organization
routes must preserve scope, avoid page-level horizontal overflow and pass an
accessibility scan.

## CIDR collection and record

The collection leads with canonical CIDR and displays VLAN ID and derived subnet
mask. CIDR opens the shared quick drawer. Overview displays CIDR, VLAN ID, subnet
mask, IPv4 broadcast address when applicable, DHCP server IP and two bounded DNS
server IP fields. Mask and broadcast are calculated by the server. The editor
accepts only CIDR, optional VLAN ID, optional DHCP server IP and optional DNS
server IPs. DHCP must belong to the CIDR.

Addresses remain a child section of the CIDR. An address can point directly to an
asset, and this is the same assignment that the asset view must edit. Wireless
and History remain lazy record sections. Name, location, gateway, description,
notes, custom assignable range and relationship-map controls are absent from the
supported interface even while their legacy columns remain temporarily for the
staged data reduction.

## Current evidence and remaining work

Focused Django network tests, collection-preference tests, all 685 frontend tests,
lint, type checking and the production build cover this boundary. Seven focused
Device and nine Networks-workspace Chromium scenarios cover the maintained
responsive layouts. The isolated real browser-to-Django-to-PostgreSQL rehearsal
passes and retains the CIDR, DHCP/DNS server facts, its IP address, Wireless and
DNS records while omitting rack, circuit, interface and MAC creation.

The maintained browser suite must continue to verify drawers, direct links,
address assignment, dirty-change guards, failed writes, focus restoration,
personal columns, touch input and responsive sections.

The route remains `in_progress`. The final read-only device projection is implemented. NetBox device/prefix
auto-adoption, the IP-only asset-side address action, DNS-provider projection, wireless
field decision, controlled legacy-data removal, technician walkthroughs and the
applicable upgrade/recovery gates remain open.
