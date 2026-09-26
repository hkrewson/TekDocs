# Phase 8 technician and assistive-technology walkthrough

This is the human acceptance record for the remaining broad responsive workspaces
under #39/#60/#75. Automated browser, API, live-runtime, production-route and
recovery evidence is indexed in `acceptance.json`; this record covers the parts
that require a person using the interface. Version remains 0.8.46.

Do not mark a workspace group's `human_review.status` complete until every profile
below has a recorded passing run for both the MSP route and an organization route.
When a group passes, add `reviewed_by` and an ISO-8601 `reviewed_at` value to its
entry in `acceptance.json`. A failed run stays pending and links its issue or note.

## Required profiles

1. **Desktop keyboard:** maintained desktop browser, 1280px or wider and a short
   viewport. Complete the journey without a pointer. Confirm visible focus, logical
   order, drawer containment, Escape/Back behavior, and restored collection focus.
2. **Touch/mobile:** real touch device or browser touch mode at 390px, with a 320px
   spot check. Confirm the software keyboard does not hide the active field or
   primary action, full-screen drawers scroll once, section selectors remain
   labeled, and no horizontal page scrolling is required.
3. **Screen reader:** VoiceOver with Safari or another maintained browser/reader
   pairing. Confirm the page, collection, status, dialog, sections, errors,
   confirmations, and return location are announced in a useful order.
4. **Zoom and long content:** native browser zoom at 200% plus long identifiers and
   values. Confirm information remains available, controls do not overlap, and
   sticky UI does not hide the active control. Record the resulting CSS viewport.

## Shared checks for every group

- Start from a collection with more than 25 records. Search for an off-page record,
  change a filter and ordering, choose 50 rows, then reset columns to defaults.
- Open a record from its name, move between sections, refresh, and use browser
  Back/Forward. Close with the backdrop or Escape on desktop and the labeled Back
  action on mobile. Confirm collection context and focus return.
- Begin an edit, attempt to leave, choose Keep editing, then repeat and Discard.
  Trigger one validation error where practical and confirm the entered values stay.
- Check loading, empty, denied/unavailable, warning, and confirmation language using
  an appropriate role or fixture. Confirm primary actions are never hover-only.
- Repeat the core open/read/return path in an organization workspace. Confirm the
  page clearly identifies the client and never exposes another client or MSP data.

## Group journeys

### Assets

Open hardware and software records. Review Overview, Specifications, Network or
Installation, Related, and History. Assign ordinary custody/status where authorized;
inspect warranty and lifecycle warnings; verify consequential disposal retains its
focused confirmation. Use Open in full page and return to the same collection.

### Contracts

Open Overview, Costs, Related, and History. Confirm currency and billing intervals
remain attached to each cost and that a user without cost permission receives an
explanation without financial values or actions. Exercise an ordinary edit and the
archive confirmation.

### Networks

Move through Networks, Wireless, VLANs, VRFs, Racks, Devices, DNS, Circuits, and
NetBox using direct links on desktop and Network views on mobile. Open at least one
parent/child path: network/address, rack/device, device/interface/IP or MAC, DNS
zone/record, and circuit/handoff. Confirm the child remains inside its parent record,
direct URLs restore the same section, and topology remains optional.

### Documentation and Files

Browse libraries, read and edit a document, protect a dirty draft, and review
templates, reusable blocks, review/publication state, history, and a PDF or managed
file. From Files, search for an off-page item, open its owning document, and use
browser Back to restore the same file result. Confirm document content owns the main
canvas while metadata and relationships remain on demand.

## Run record

Add one row per group/profile. Keep failures in the table until their linked issue
passes a later run. Store no credentials, client data, or screenshots containing
sensitive values.

| Date | Commit | Group | Profile and environment | MSP | Organization | Result | Reviewer | Evidence / issue |
|---|---|---|---|---|---|---|---|---|
| _pending_ |  | Assets | Desktop keyboard |  |  |  |  |  |
| _pending_ |  | Assets | Touch/mobile |  |  |  |  |  |
| _pending_ |  | Assets | Screen reader |  |  |  |  |  |
| _pending_ |  | Assets | Zoom and long content |  |  |  |  |  |
| _pending_ |  | Contracts | Desktop keyboard |  |  |  |  |  |
| _pending_ |  | Contracts | Touch/mobile |  |  |  |  |  |
| _pending_ |  | Contracts | Screen reader |  |  |  |  |  |
| _pending_ |  | Contracts | Zoom and long content |  |  |  |  |  |
| _pending_ |  | Networks | Desktop keyboard |  |  |  |  |  |
| _pending_ |  | Networks | Touch/mobile |  |  |  |  |  |
| _pending_ |  | Networks | Screen reader |  |  |  |  |  |
| _pending_ |  | Networks | Zoom and long content |  |  |  |  |  |
| _pending_ |  | Documentation/Files | Desktop keyboard |  |  |  |  |  |
| _pending_ |  | Documentation/Files | Touch/mobile |  |  |  |  |  |
| _pending_ |  | Documentation/Files | Screen reader |  |  |  |  |  |
| _pending_ |  | Documentation/Files | Zoom and long content |  |  |  |  |  |

## Closure

Phase 8 closes only after all four groups are human-reviewed, the production image
and supported recovery/upgrade gates pass for the release candidate, and release
approval is recorded. Deployment and publication remain separately authorized.
