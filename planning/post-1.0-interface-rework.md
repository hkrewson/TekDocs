# Post-1.0 interface rework

Status: second reference pass implemented and automated evidence complete; hands-on acceptance pending.

The first pass proved route, permission, and recovery compatibility but did not
materially reduce interface complexity. Maintainer review therefore rejected the
horizontal local-navigation row and the permanent exposure of setup, diagnostic,
repository, and metadata terminology. The second pass keeps the compatibility
boundary while changing the working hierarchy:

- the active hub's destinations expand in the fixed sidebar instead of occupying
  a second navigation bar above every page;
- Home contains a conditional first-organization setup action and a real reminder
  queue; Activity remains available by direct link and System status but is not a
  primary Home destination;
- Knowledge opens Documents directly. Templates and Files are supporting views
  selected within Knowledge, while repository tooling is in **More** and the
  actionable **Needs attention** queue appears only when findings exist or its
  deep link is active;
- Assurance contains Compliance; Recycle bin moves to Manage;
- Manage exposes Integrations, Data model, and Recycle bin. Data model presents
  Fields and **Categories and tags** as related views while retaining the existing
  custom-field and taxonomy routes;
- existing personal Settings remains in the account menu. A future workspace
  settings destination must contain real workspace controls before it is added.

The first bounded slice is **Reference Shell, Documentation, and Assets**. It
changes the information architecture and two representative workflows without
changing backend APIs, authoritative model shape, capability identifiers,
authorization rules, or the existing deep-link contract. Broader rollout requires
explicit human acceptance of this slice.

## Navigation contract

The primary navigation is a fixed task-hub registry layered over the existing
capability registry. A hub is visible only when at least one of its children is
authorized. Selecting a hub opens its first authorized child in the order below.

| Hub | Ordered children |
| --- | --- |
| Home | Overview (Reminders and Activity remain compatible contextual routes) |
| Clients | Organizations, People, Sites |
| Knowledge | Documentation, Files |
| Operations | Assets, Licenses, Networks, Domains, Certificates, Credentials |
| Business | Services, Vendors, Products, Invoices, Stock |
| Assurance | Compliance |
| Manage | Integrations, Data model, Recycle bin (Taxonomies remains the Categories and tags route inside Data model) |

Personal settings, staff, access control, notification delivery, and system
status remain in the permission-aware account menu. Workspace capabilities and
permissions remain the source of truth. Omitting a link is not an authorization
decision; the server continues to enforce every request.

Desktop uses a solid 244px sidebar. The active hub expands its authorized primary
destinations directly below the hub label. At 800px and below the same hierarchy
appears in the focus-trapped sidebar overlay; there is no duplicate section row or
selector above the page. Existing workspace switching, global search,
notifications, account actions, skip navigation, focus transfer, and denial
behavior remain intact.

## Route and entry-point inventory

Every capability route has an MSP form and, where its capability scope permits,
an organization form at
`/workspaces/organizations/:organizationId/<route>`. Organization visibility is
the capability list returned for that workspace. MSP invoice and stock entries
add the noted permissions.

| Hub | Route | Entry and authorization condition | Primary task entry |
| --- | --- | --- | --- |
| Home | `/overview` | all authorized workspaces | review workspace summary |
| Home (contextual) | `/deadlines` | `deadlines` capability | review reminders |
| Home (administrative) | `/activity` | `activity` capability | review activity |
| Clients | `/organizations` | MSP `organizations` capability | create or open organization |
| Clients | `/people` | `people` capability | create or open person |
| Clients | `/sites` | `sites` capability | create or open site |
| Knowledge | `/documentation` | `documentation` capability | New document |
| Knowledge | `/files` | `files` capability | add or open file |
| Operations | `/assets` | `assets` capability | New asset |
| Operations | `/licenses` | `licenses` capability | new license |
| Operations | `/networks` | `networks` capability | new network record |
| Operations | `/domains` | `domains` capability | new domain |
| Operations | `/certificates` | `certificates` capability | new certificate |
| Operations | `/credentials` | `credentials` capability | new credential reference |
| Business | `/services` | `services` capability | new service or contract |
| Business | `/vendors` | `vendors` capability | new vendor |
| Business | `/products` | `products` capability | new product |
| Business | `/invoices` | `invoices` capability and `invoices.issue` at MSP | invoice settings or draft |
| Business | `/stock` | MSP `stock` capability and `invoices.view` | stock review |
| Assurance | `/compliance` | `compliance` capability | review requirements |
| Manage | `/recycle-bin` | `recycle_bin` capability | restore eligible record |
| Manage | `/integrations` | `integrations` capability | add or inspect integration |
| Manage / Data model | `/custom-fields` | `custom_fields` capability | new custom field |
| Manage / Data model | `/taxonomies` | MSP `taxonomies` capability | new category definition |

The following are account-menu or shell routes rather than task-hub children:
`/settings` (signed-in user), `/staff` (`staff_invitations.view`),
`/access-control` (`memberships.assign_role`), `/notification-delivery`
(`notifications.manage`), `/system-status` (`system_diagnostics.view`), and
`/search` (active workspace search). `/accounting` and the organization accounting
route remain compatibility redirects to invoices. Unknown or
unauthorized destinations retain the existing unavailable/redirect behavior.

### URL state that must survive

- Documentation collection: `doc_library`, `doc_q`, `doc_category`, `doc_type`,
  `doc_collection`, `doc_tag`, `doc_health`, `doc_order`, and `doc_page`.
- Documentation record: `document`, `document_view`, `document_history_page`,
  `document_revision`, `publication`, `publication_section`, and `repository`.
- Assets collection: `search`, `kind`, `status`, `assigned`, `warranty`, `site`,
  `ordering`, `page`, and `page_size`.
- Asset record: `preview` or `record`, plus `section`. Browser navigation state
  retains the collection scroll position and focus return target.
- Global search and all other existing feature-owned query parameters remain
  untouched by hub navigation. Current paths remain canonical for this slice.

## Baseline and reference journeys

The pre-slice shell exposed five collapsible groups and 24 capability links.
Each destination was directly available, but the user had to scan a mixed list
of pages and remember collapsed state. Documentation separately exposed document,
template, repository, health, source, key, reuse, review, publication, and history
actions with competing prominence. Assets already had the desired collection →
quick drawer → optional full-page pattern and therefore serves as the preservation
reference rather than a structural rewrite.

The acceptance comparison records:

- primary-navigation actions and duplicate destinations;
- collection-to-record actions;
- modal, drawer, and full-page transitions;
- close, refresh, direct-link, back/forward, conflict, denial, and discard paths;
- focus restoration and retained filters, section, selection, and scroll position.

No step-count improvement is claimed until the maintainer completes the hands-on
walkthrough. The baseline is a compatibility boundary, not a target to game by
hiding required actions.

## Reference workflow contract

Knowledge has one primary destination: **Documents**. A compact Knowledge view
selector reaches **Templates** and **Files** without a horizontal tab row or more
sidebar entries. Search stays visible, filters remain in the shared filter menu,
and **New document** is the single primary collection action. Import and repository
work are subordinate in **More**. **Needs attention** is a visible collection
queue only when findings exist; its existing content-health deep link remains
valid. A selected document exposes
**Content**, **Files**, **Links**, **Review and publication**, and **History** as
applicable. Repository source operations remain contextual. Canonical Markdown,
dirty-state protection, revision conflicts, independent review, publication
authorization, retained files, and Git evidence are unchanged.

Assets retains its collection, quick drawer, and optional full-page path. Search
and the shared filter menu remain visible. **New asset** is primary; CSV transfer
and column configuration are utilities. Hardware and software records retain
Overview, Specifications, Documentation, Network or Installation, Related, and
History. Opening, editing, closing, refreshing, and direct linking must preserve
collection state, section, scroll position, and focus.

## Acceptance criteria

- Hub filtering and deterministic default destinations follow authorized
  capabilities without changing server authorization.
- Existing routes and the query/state contract above survive direct links,
  refresh, back/forward navigation, workspace changes, and denial.
- Documentation and asset reference journeys preserve the behavioral contracts
  above, including conflict and unsaved-change recovery.
- Desktop, 320/390/768/1024/1280/1440px layouts, 200% zoom, keyboard-only use,
  touch targets, and WCAG 2.2 automated checks pass.
- The existing frontend gate, lint, type checking, API contract check, production
  build, untranslated-control checks, and Docker runtime checks pass.
- The single existing `tekdocs` Compose project is used. No parallel project,
  database, or data volume is created.
- The operator fixture contains MSP, client and vendor workspaces, mixed hardware
  and software assets, Git-backed documents, templates, retained publications,
  and permission-limited users. Conflict is created during the walkthrough so its
  recovery can be observed rather than pre-resolved in fixture data.
- The maintainer completes and approves
  [the reference acceptance walkthrough](post-1.0-interface-reference-acceptance.md)
  before shared patterns are extracted or another hub is migrated.

## Bounded rollout after acceptance

Extract only demonstrated patterns: hub/local navigation, page header/action
hierarchy, collection toolbar, record sections, forms, status messages,
confirmation dialogs, and empty/error states. Roll out Clients, remaining
Knowledge, remaining Operations, Business, Assurance, Manage, then authentication
and client portal. Each is a separate completed roadmap slice with aligned tests,
Wiki updates, runtime evidence, known-risk disposition, and one descriptive commit.
Any required API or persistence change receives its own contract, migration,
authorization, and compatibility review.

## Clients rollout

The approved reference direction now extends to Organizations, People, and
Sites. These pages use one compact collection pattern: the record count sits
with the page title, search remains visible, filters and column choices remain
secondary, and the table contains records rather than a repeated set of row
actions. Opening a record is the single way into its workflow.

Organization records keep **Open workspace** and **Edit details** visible;
billing, fields, and archive are in **More**. Person and site records keep
**Edit details** visible and place infrequent or destructive actions in
**More**. Site locations retain their contextual add and per-location action
menu because those operations belong to the selected site rather than the
collection. People search, field filter, ordering, and page state now survive a
direct link or refresh. Existing authorization, denial, archive confirmation,
dirty-state protection, and record URLs remain unchanged.

Acceptance requires unit and browser coverage for search, filtering, sorting,
direct links, record opening, create/edit/archive recovery, workspace isolation,
keyboard use, responsive layout, and accessibility. No backend or persistence
change is part of this slice.

## Remaining Knowledge rollout

Knowledge now opens Documents directly and no longer expands a second Files link
in the sidebar. Documents, Templates, and Files are related working views selected
through one compact control that remains usable on narrow screens. Existing
`/files`, `doc_library=templates`, and `doc_library=health` links remain valid,
including the files-only capability fallback.

The document collection places its count with the page title and removes the
repeated section heading. Content findings are presented as **Needs attention**
beside search and filters, not as a vague destination under **More**. Repository
content opens as its own focused authoring workspace, without a duplicate Documents
header above it. The Files collection removes explanatory text already implied by
the context and makes the file name itself the download action; the owning document
remains the management path.

Acceptance requires deterministic permission-filtered hub behavior, retained deep
links and URL state, unsaved-change protection while changing views, responsive and
keyboard access to every Knowledge view, complete file ownership links, repository
focus restoration, and unchanged Git evidence and authorization behavior. No API,
schema, or persistence change is part of this slice.

## Remaining Operations rollout

Licenses, Networks, Domains, Certificates, and Credential links now follow the
compact collection hierarchy demonstrated by Assets. The page heading owns the
record count, so collections no longer repeat a directory heading or explanatory
sentence before the first task. Search remains visible, Domain status moves into
the shared filter menu, and each row remains the single entry to its record or
quick drawer. Create actions remain the only primary collection actions.

Consequential guidance remains where it changes a decision: Credential links keep
the 1Password storage boundary, domain monitoring stays distinct from entered
registration data, and certificate checks retain their evidence and validation
limits. Existing collection parameters, direct record links, dirty-state recovery,
permission denials, monitoring actions, and Assets' drawer/full-page behavior are
unchanged. This slice does not alter backend APIs, persistence, or authorization.

Acceptance requires focused component coverage for collection loading, filtering,
sorting, paging, direct off-page records, create/edit recovery, and denial; browser
coverage must confirm the compact hierarchy and usable controls at desktop and the
required narrow widths.

## November 15, 2026 implementation evidence

Verified:

- all 889 frontend unit/component tests pass with the repository coverage gates;
- lint, type checking, generated API agreement, the production build, CSP checks,
  untranslated-control coverage, and bundle budgets pass;
- 60 reference shell/document browser cases pass across the six required widths,
  including Git-backed document and publication recovery paths;
- eight Chromium/WebKit responsive cases pass across the required widths and
  200% zoom, including mobile navigation focus behavior;
- 15 focused Chromium journeys pass for Clients and workspace switching,
  including the new hub-to-destination behavior, URL-derived workspace state,
  create/edit/archive recovery, denial, keyboard use, and axe checks;
- the Organization record remains free of horizontal overflow and axe findings
  at both 1440px and the required 320px minimum width;
- 36 focused Chromium Knowledge and shell journeys pass, including all six review
  widths for Needs attention, all Files collection widths, direct links, ownership
  links, hub defaults, and axe checks; the 320px and 1440px Knowledge collections
  were also visually inspected;
- 92 focused Chromium Operations journeys pass across the required widths for
  licenses, networks, domains, certificates, credential links, and the surrounding
  shell; all 889 frontend unit/component tests, lint, type checking, and the
  production bundle gate remain green;
- the rebuilt frontend and backend are healthy in the existing `tekdocs`
  Compose project; no parallel project or data volume is in use;
- the retained development tenant preserves its existing owner and now contains
  three verified acceptance workspaces; each has 31 mixed assets, 30 contracts,
  30 networks, 30 Git-backed documents, one fragment, and 32 checksum-verified
  managed files, plus limited users and a retained client publication;
- the public Wiki checkout passes all 37 required pages and 55 total pages.

The second reference pass additionally verifies 35 focused Chromium browser
journeys for the revised shell, conditional document health, Data model, and
integration review queue. Eight responsive Chromium/WebKit journeys pass across
the six review widths and 200% zoom. The final production image passes its bundle
budget and is healthy at port 3200 in the retained `tekdocs` Compose project.

The existing development database reproduced a pre-existing schema drift: an
obsolete `core_contentinclude.resolved_markdown` column, absent from every current
model and migration state, remained `NOT NULL` and blocked current content-index
writes. Data-integrity work therefore preempted the reference fixture. Migration
0226 removes that column only when present; it is a no-op on authoritative fresh
schemas and has an upgrade-path regression test. This does not change the current
API or persistence contract.

The migration applied successfully to the retained development database and
removed the obstructing column. Migration drift, Ruff, and Django deployment
checks pass (with the existing local HTTP and OpenAPI operation-name warnings).
The regression test is committed for hosted CI; local execution is blocked by
the required runtime-role prohibition on creating and migrating test databases,
and repository policy forbids creating a parallel local database service.

Inferred: the asset collection remains compatible because its established
collection, drawer, full-record, shared-filter, focus, and URL-state patterns were
preserved rather than structurally rewritten, and its existing unit coverage
passes. The hands-on walkthrough remains the product-clarity check.

Blocked pending maintainer action: shared-pattern extraction and the Clients
rollout must not begin until the reference acceptance walkthrough is approved.
