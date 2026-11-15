# Reference interface acceptance walkthrough

Use this walkthrough only with the existing local `tekdocs` Docker project. Do
not create another Compose project, database service, or data volume. The fixture
must contain an MSP, two clients, a vendor, hardware and software assets,
Git-backed documents, templates, publication states, and the owner, reviewer,
assigned read-only, and client users. Record failures; do not weaken a check to
make it pass.

Open `http://localhost:3200`. Use the existing local owner account for owner
steps. The preparation process writes the synthetic reviewer, assigned reader,
and client credentials to the private ignored file
`artifacts/interface-reference-acceptance/access.txt`; never copy that file into
source control or acceptance notes. Enroll MFA when a synthetic account first
requests it.

## Result

- [ ] Approved for shared-pattern extraction and bounded rollout
- [ ] Changes requested; notes are recorded below

Reviewer: ____________________  Date: ____________________

## 1. Shell and workspace boundaries

- [ ] Sign in as the owner and confirm the sidebar contains exactly Home,
  Clients, Knowledge, Operations, Business, Assurance, and Manage.
- [ ] Open each hub. Confirm it lands on the first visible local section and the
  local navigation lists only pages available in the active workspace.
- [ ] Switch from the MSP to Acceptance A, then to Acceptance B, and back. Confirm
  the hub and local navigation update without showing inaccessible pages.
- [ ] Open the account menu. Confirm Settings, Staff, Access control, Notification
  delivery, and System status appear only when permitted and are absent from the
  task hubs.
- [ ] Use global search, notifications, the skip link, and the account menu. Confirm
  focus moves to the destination and returns to the trigger when an overlay closes.
- [ ] Paste a direct URL containing filters or a selected record, refresh it, then
  use Back and Forward. Confirm the URL and visible state agree after every action.

## 2. Documentation collection

- [ ] Open Knowledge. Confirm it lands on Documentation and shows Documents,
  Templates, Repository, and Content health.
- [ ] Confirm search is visible, filters use one Filters menu, and New document is
  the only primary collection action. Import Markdown and repository actions must
  remain visibly secondary.
- [ ] Search for `Acceptance A Runbook`, apply a category or health filter, change
  sorting, and move to another page. Refresh and use Back/Forward. Confirm the
  search, filter, order, page, and selected document are retained.
- [ ] Open Templates and confirm an acceptance template is available. Return to
  Documents without losing the collection state.
- [ ] Open Repository and a Git-backed document. Confirm repository evidence and
  source operations remain available without replacing the normal authoring path.
- [ ] Open Content health. Confirm loading, populated, empty, and retry/error
  messages occupy the content area without shifting the shell.

## 3. Document record, recovery, and publication

- [ ] Open a document and confirm its applicable sections are Content, Files,
  Links, Review and publication, and History.
- [ ] Edit Markdown, try to leave without saving, and choose Stay. Confirm the edit
  remains. Try again and choose Discard. Confirm the accepted revision returns.
- [ ] In two browser tabs, open the same document. Save a change in the first tab,
  then save a different change in the second. Confirm a conflict is shown, neither
  version is silently lost, and the recovery choice is understandable.
- [ ] Confirm files and links remain attached after saving and refreshing.
- [ ] As the owner, submit a publication for review. Confirm the owner cannot satisfy
  an independent approval that requires another authorized person.
- [ ] Sign in as the reviewer, review the evidence, and approve. Confirm the
  publication state and History update. Verify the client user sees only the
  authorized client publication and retained downloads.
- [ ] Open More. Confirm repository/source, key, export, or settings actions appear
  only when relevant and destructive actions remain visually separate.

## 4. Asset collection and record

- [ ] Open Operations. Confirm it lands on Assets, search is visible, all filter
  dimensions are in the Filters menu, and New asset is the primary action.
- [ ] Confirm CSV transfer and column configuration are secondary utilities.
- [ ] Filter to hardware, change ordering and page size, then open an asset in the
  quick drawer. Close it and confirm the same row, filters, order, page, scroll
  position, and keyboard focus are restored.
- [ ] Reopen the drawer and choose the full-page record. Use Back and Forward,
  refresh, and paste the record URL into a new tab. Confirm the selected section
  and collection state remain stable.
- [ ] For hardware, check Overview, Specifications, Documentation, Network,
  Related, and History. For software, confirm Installation replaces Network.
- [ ] Edit a safe field, save, refresh, and confirm the record and collection row
  agree. Trigger a recoverable load failure and confirm Retry works without losing
  the collection state.

## 5. Denial and limited users

- [ ] Sign in as the assigned read-only Acceptance A user. Confirm Acceptance B is
  absent, write actions are absent, and a pasted Acceptance B URL is denied.
- [ ] Confirm the limited user sees only hubs and local sections backed by returned
  capabilities. Direct API or deep-link attempts must not broaden access.
- [ ] Sign in as the client user. Confirm the client portal still uses its existing
  navigation and exposes only approved client content.

## 6. Responsive, keyboard, zoom, and accessibility

- [ ] At 320, 390, and 768px, open the navigation overlay. Confirm focus is trapped,
  Escape closes it, focus returns to Open navigation, and the page does not scroll
  behind the overlay.
- [ ] At those widths, use the labeled section selector and confirm it changes the
  local page without losing workspace or query state.
- [ ] At 1024, 1280, and 1440px, confirm the sidebar remains solid and stable and
  the local navigation does not wrap over page actions.
- [ ] At 200% zoom, complete one documentation edit and one asset drawer journey.
  Confirm there is no horizontal page overflow or hidden primary action.
- [ ] Complete the shell, document, and asset journeys using only the keyboard.
  Confirm visible focus, logical order, useful names, and restored focus.
- [ ] Confirm automated WCAG 2.2 checks report no violations on the shell,
  documentation collection/record, asset collection/drawer/record, denial, empty,
  error, and confirmation states.

## Notes and requested changes

- Navigation/task clarity:
- Documentation workflow:
- Asset workflow:
- Denial and recovery:
- Responsive/accessibility:
- Required changes before approval:
