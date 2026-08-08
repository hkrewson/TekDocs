# ADR 0009: Structured sites and locations

- Status: Accepted
- Date: 2026-08-08

## Decision

Represent a `Site` as an addressable physical or operational place owned by exactly one workspace: the MSP or one organization. A site carries address, timezone, contact-phone, and operator-defined code metadata. Represent smaller addressable places as `Location` records inside a site. Locations form a parent-child tree and use a bounded kind vocabulary: building, floor, suite, room, office, desk, or area.

Both records use stable Entity identities whose tenant and organization scope exactly match their typed record. A location and its parent must belong to the same site and workspace. Application validation prohibits cycles, while PostgreSQL scope guards reject mismatched tenant, organization, entity, site, and parent relationships.

Sites and locations may be archived but are not destructively deleted through the application. Archiving a site archives its active location tree; archiving a location archives that location and its descendants. Existing references remain valid for historical display, while new placement choices include only active records.

Person associations receive optional site and structured-location references. The selected records must belong to the association's URL-derived workspace, and the location must belong to the selected site. The existing `location` and `office` strings remain canonical fallback/display snapshots in the `0.1.x` line so imported values, remote work, unmapped desks, and references to later-archived places remain understandable. Selecting a structured place refreshes those labels; clearing it does not silently erase operator-authored labels.

Site/location records are descriptive inventory, never an authorization boundary. Client access continues to be decided by the future policy service and explicit user assignments.

## Consequences

- MSP employees and organization contacts can share the same placement vocabulary without weakening workspace isolation.
- Later assets, racks, networks, wireless records, and diagrams can reference stable site/location entities rather than copying address strings.
- Moving a location between sites is not supported in `0.1.6`; operators create the replacement and archive the old placement so historical references are not silently reinterpreted.
- Geocoding, maps, floor plans, rack inventory, and arbitrary custom location kinds remain outside this slice.
