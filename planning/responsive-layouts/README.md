# Pre-1.0 responsive layouts and record navigation

Required 1.0 acceptance under #60; coordinates with #40 and #39 and preserves #75/#76 obligations. Version remains 0.8.46. No deployment or publication implied.

## Accepted interaction contract

Balanced lists; personal feature-specific column choices in curated order; immutable identity column; 25/50/100 rows, default 25. Whole-collection authorized search/filter/sort with deterministic ties. Current-page bulk selection only; query/order/page changes clear it. Shared filter menu plus active-condition summary. URL-addressed query, preview, record and section state, with list scroll/focus restoration.

Record names open a full record workspace in a right overlay drawer (full-screen below 768px), with background locked and one scrolling body. This explicitly supersedes the original short-preview/no-tabs rule following user validation. Assets implements this revised contract first. Remove the duplicate row-level Open record link; retain an optional Open in full page link within the drawer for bookmarks/new tabs. Drawer and full-page views share record content and section editing; do not open nested record drawers. Backdrop clicks and Escape dismiss the drawer through the shared edit guard; full-screen mobile uses a feature-specific Back link instead of a Close button. Record tabs: Overview first, active section editor with Save/Cancel; mobile Sections menu. Dirty navigation offers Keep editing/Discard. Preserve failed writes and never blindly retry uncertain mutations. Major actions keep existing review/confirmation workflows. Urgent issues remain on Overview. Existing permission and data-integrity policy remains authoritative.

## Delivery

Delivery is organized around complete user-facing areas. Related routes are audited together, share one interaction contract, and are accepted as one milestone. Focused checks run while the milestone is being built; the broad project, browser, and live-stack gates run once at the milestone boundary unless a cross-cutting change justifies an earlier run. Small standalone follow-ups are reserved for data-integrity, authorization, or release blockers rather than routine visual refinements.

1. **Inventory and foundation** — Route/state inventory, shared list, overlay preview, URL state, tabs, dirty-form protection through Assets. Status: in progress; API and navigation/edit-protection foundations implemented.
2. **Assets** — Complete reference layout, operational overview, focused sections in a full record drawer and optional full page. Status: in progress; collection, previews and tabbed records implemented, acceptance and remaining actions open.
3. **Contracts and Networks** — Validate the shared patterns against costs and connected network records. Status: in progress; Contracts, the simplified Networks page and its child Addresses/Wireless sections and workspace-wide Wireless, VLAN and VRF registers with associated subnet navigation, Racks and Devices core record drawers with parent-scoped interface editing and IP/MAC assignment migrated; DNS zone/record drawers, focused editing, history and record transfers verified against PostgreSQL and the live browser; circuit register/service-detail editing and handoff browsing verified as a bounded checkpoint; remaining network object surfaces and acceptance open.
4. **Operational records** — Organizations, vendors, people, sites, products, licenses, stock, domains, certificates, credential references. Status: accepted; the grouped Organizations/People/Sites milestone and connected Stock/Vendors/Products/Licenses milestone pass their responsive and real-stack acceptance.
5. **Documentation and files** — Libraries, reader/editor, templates, blocks, maps, reviews, publications, exports and files. Status: in progress; document library/reader and template/reusable-content workflows implemented; broader acceptance remains open.
6. **Financial and integration workflows** — Invoices, recurring workflows, compliance/data flows, integrations/imports/webhooks and exceptions. Status: pending.
7. **Shell and remaining surfaces** — Search, overviews, reminders, activity, notifications, recycle bin, metadata, account/access/setup/help/system status and client portal. Status: pending.
8. **Release acceptance** — Route/state completion, technician walkthroughs, production image and release gates. Status: pending.

Separate work items cover navigation, collection APIs and personal preferences. Every migrated surface must remove its prior competing layout. Current shell routes are listed in routes.json from App.tsx; authentication, portal, and nested record/workflow states still need expansion during Phase 1; state/viewport requirements are specified in acceptance.json, and evidence must be recorded explicitly before marking a surface complete.

## APIs and compatibility

Additive bounded summary collections preserve legacy APIs. Detail/tab data loads on demand. Personal preferences are authenticated, installation/user/feature scoped, contain only column identifiers and page size, and have safe defaults. Django migrations and reviewed RLS classification govern persistence. Preserve existing links, contracts and operation IDs; regenerate OpenAPI/types for intentional additions.

## Acceptance

Docker make check plus focused API/component/browser tests per slice. Real backend journeys for migrated workflows. Final production-image, upgrade/recovery and release gates. Test 320/390/768/1024/1280/1440px, short heights, 200% zoom, keyboard/touch and maintained engines. Explicitly cover denied, stale, conflicts, dirty forms, permission changes, large collections, off-page search, stable sorting, bounded queries, focus/history restoration, deep links and missing records. No horizontal page overflow. Specialized code/table/PDF/topology scrolling requires a recorded reason.

Excluded: named saved views, resizable/reorderable columns, density modes, infinite scrolling and cross-page selection. Existing security/recurring/pilot obligations remain open. User and demo data must be preserved.

## Implementation records

- [Operational records milestone](operational-records.md)

- [Stock collection and record workspace](stock-workspace.md)

- [Vendor collection and supplier record workspace](vendor-workspace.md)

- [Product catalog collection and record workspace](product-workspace.md)

- [License collection and record workspace](license-workspace.md)

- [Wireless site and VLAN assignment](wireless-site-vlan-assignment.md)
- [VLAN and VRF registers](addressing-registers.md)

- [Wireless parent-network assignment](wireless-parent-assignment.md)

- [Workspace Wireless register](wireless-register.md)

- [Wireless records within network drawers](network-wireless.md)

- [Addresses within network records](network-addresses.md)

- [Networks collection and record workspace](networks-layout.md)

- [Contracts collection and full record workspace](contracts-layout.md)

- [Refresh routing and public addresses](frontend-routing.md)

- [Full asset record drawer](asset-record-drawer.md)

- [Software asset audit history](software-history.md)

- [Shared record navigation](record-navigation.md)

- [Assets site filtering](asset-site-filter.md)

- [Assets reference layout](assets-layout.md)

- [Personal collection preferences](personal-preferences.md)
- [Navigation and edit protection](navigation-foundation.md)
- [Assets collection API and next integration dependencies](asset-collection.md)
- [Implementation issues](issues.json)
- [Progress and verification](progress.md)

- [Devices and racks collection prerequisite](inventory-collections.md)

- [Rack register and complete drawer](rack-register.md)

- [Devices register and core editing](device-register.md)

- [Device hardware replacement](device-hardware.md)

- [Interfaces within device records](device-interfaces.md)

- [Interface IP/MAC records and assignment](interface-endpoints.md)

- [Device relationships within device records](device-relationships.md)

- [DNS register and records within zone drawers](dns-register.md)

- [DNS record transfer between zones](dns-record-transfer.md)

- [Circuit register, service-detail drawers and bounded provider/contract choices](circuit-register.md)
