# Devices documentation register

Phase 3/8 (#80/#60), required pre-1.0 under #75. Version remains 0.8.46.
The product boundary is [the 2026-09-28 network documentation decision](../network-documentation-boundary.md).

## Supported projection

Devices is a read-only Networks view backed by existing asset and NetBox identity
records. It is documentation of imported equipment, not a second device-management
system. The register's curated columns are device name, NetBox ID, rack, starting
position, height in U, serial number and model. Search covers those asset facts,
manufacturer/product/model names and numeric NetBox IDs across the authorized
collection. Personal column and page-size preferences remain bounded to this set.

A rack is displayed only as an imported fact. There is no rack collection, rack
editor or rack-placement workflow in the supported interface. The Devices view
also has no New device, edit, hardware-replacement, placement, interface, MAC,
relationship or status-management controls. Existing backend records and APIs are
retained temporarily for compatibility and controlled migration, but their former
UI is outside the product boundary.

Names open the shared quick drawer. Overview shows NetBox ID, rack, position,
height, serial, manufacturer, product, model and the most recent source observation.
History remains available as evidence. The full-record URL, direct section URL,
refresh, Back/Forward behavior, focus restoration, mobile section selector and
backdrop/Escape dismissal follow the shared layout contract.

Asset permission remains authoritative. A user without asset visibility receives
no hardware identity, serial, manufacturer, product or model values, and those
values are excluded from search. Network facts that are safe under Networks view
permission remain visible.

## Source and adoption boundary

NetBox sync is responsible for automatically adopting a NetBox device as the
necessary hardware Asset plus its Devices projection when an eligible source
record has not already been linked. Model and manufacturer are reused or created
from the provider facts only through that reviewed import service. Repeated syncs
must update the same linked identities and must not create duplicates. Automatic
adoption is the next implementation slice; this checkpoint establishes the
read-only destination it will populate.

## Verification

Focused Django tests cover projection fields, serial/NetBox search, stable ordering,
permission redaction, preferences and workspace isolation. Component and browser
coverage exercises the seven curated columns, quick drawer, History, direct URLs,
legacy-section fallback, keyboard/touch use, 320/390/768/1024/1280/1440 widths,
short heights, 200% zoom and no horizontal page overflow. The live workspace
rehearsal confirms that manual device creation and the removed network-management
surfaces are absent.
