# Full asset record drawer — pre-1.0, 0.8.46

Scope: #79 under #77/#60, coordinated with #78/#40. User testing found the short preview repeated the row and added an unnecessary Open record step. The user explicitly approved replacing it with the full record workspace. This revises the accepted interaction contract; it does not close Assets, the foundation, or whole-application acceptance.

## Interaction and implementation

Click an asset name to open Overview in an overlay up to 64rem wide (90% of the viewport), or full screen below 768 CSS pixels. The list retains its width and context behind the locked background. The drawer header contains the asset name and Close; one body scrolls. Long names have a Full name disclosure. There is no row-level Open record link.

The drawer renders the same AssetRecord used by the full page: Overview; Specifications; Network for hardware or Installation for software; permission-filtered Related; and History. Existing operational facts, warnings, editors, confirmations, relationships, and deferred history remain available. It omits the redundant full-page heading and uses the shared section links/mobile Sections menu. Open in full page is an optional drawer action retaining the selected section, including history pagination, with a real URL supporting a new tab.

HardwareAssignment is shared by both presentations. It retains loading/retry, site/location consistency, server-authoritative lifecycle reconciliation, and failed-draft behavior from the former quick assignment. The separate quick status form and duplicate assignment implementation are removed. Ordinary status changes use Edit details; disposal retains its focused confirmation and server rules. Busy hardware detail/disposal fields are disabled while the shared guard protects navigation; uncertain mutations are never automatically retried.

## Navigation, data, and compatibility

Existing `preview=<id>` links now open the full drawer. Existing `record=<id>` links still open the full page. Both accept `section` and applicable `history_page`; omission selects Overview. Sections preserve list search/filter/order/page/columns and transient browser navigation state. Close/Escape explicitly replaces the current drawer location with the collection, even after several section changes. Browser Back/Forward continues to traverse visited sections; previous browser entries are not erased. A direct full-page record still has Back to assets.

The shared dirty/busy guard applies to drawer close, sections, full-page transitions, browser navigation, and unload. Keep editing preserves values; Discard changes completes the requested transition. Only one section editor is mounted. Failed writes retain drafts without automatic retries. Existing focused confirmations remain; related record drawers are not nested.

Bounded collection summaries, selected-record detail loading, on-demand history/relationships, authorization and business endpoints are unchanged. This is a presentation change: no domain migration, preference schema change, OpenAPI/generated type change, ownership/RLS reclassification or recovery-format change is needed.

## Verification and remaining work

Executable evidence lives in Assets.test.tsx, asset-layout.spec.ts, asset-edit-navigation.spec.ts, and live-workspace.spec.ts. Coverage includes failed status/details saves; failed assignment writes and choice loading; pending-save protection; section/full-page dirty transitions; drawer sections, refresh, Back/Forward, and Close after section changes; preserved full-page section links; focus restoration and filter departures; all six widths across three engines; accessibility scans and touch/CSS zoom stress. The live journey edits hardware, assigns it, and saves network addresses in the drawer, retaining full-page verification and independent PostgreSQL fixture assertions.

Gate results are recorded in progress.md. Native screen-reader/mobile-keyboard/zoom technician walkthroughs, Contracts/Networks validation, remaining inventory states and production/recovery/release gates remain open. Local app refresh is authorized for this checkpoint; production deployment, push and Wiki publication remain separate. Version stays 0.8.46.
