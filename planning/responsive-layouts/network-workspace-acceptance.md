# Networks combined workspace acceptance

Phase 3/8 (#80/#60), required pre-1.0 under #75. Version remains 0.8.46.

## Accepted automated boundary

The Networks entry point now treats Networks, Wireless, VLANs, VRFs, Racks,
Devices, DNS, Circuits, and NetBox as one responsive set of workspace views. At
768 CSS pixels and above, the views remain direct links with an indicated current
view. Below 768 pixels, the nine-link strip becomes one labeled Network views
selector. Each choice retains its direct `?view=` URL, browser navigation, and
MSP or organization path. This removes a tall, wrapping navigation block from
phone layouts without hiding any register.

`network-workspace-acceptance.spec.ts` traverses every view instead of inferring
route readiness from isolated register tests. It covers 320, 390, 768, 1024,
1280, and 1440 CSS-pixel widths; a short 520-pixel viewport; the 640-CSS-pixel
viewport exposed by a 1280-pixel display at 200% browser zoom; and MSP plus
organization routes. Every view must load a bounded collection state, preserve
its URL, avoid page-level horizontal overflow, and pass an accessibility scan.
Organization checks assert that all nine data requests stay inside the exact
client workspace and that no MSP collection request is made.

The complete existing `network-layout.spec.ts` suite remains part of this
checkpoint. It continues to verify network and wireless record drawers, full-page
links, child addresses, assignment changes, dirty-change guards, failed writes,
focus restoration, personal columns, touch input, and responsive record sections.

## Evidence and remaining work

All 195 combined layout cases pass in Chromium, Firefox, and WebKit: 168 existing
network/record cases and 27 whole-workspace cases. Focused lint, TypeScript, and
Networks component checks pass. The local 0.8.46 frontend image was rebuilt so
the selector can be reviewed at `http://localhost:3200`.

The MSP and organization Networks routes remain `in_progress` in the route
inventory because human technician and assistive-technology walkthroughs, final
recovery/release gates, and release approval are still outstanding. The
production-image refresh boundary is already covered separately by
[production-route-acceptance.md](production-route-acceptance.md). No API, schema,
migration, permission, domain-data, deployment, or version change is included.
