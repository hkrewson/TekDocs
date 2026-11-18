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

## Business rollout

Services, Vendors, Products, Invoices, and Stock follow the same compact
collection hierarchy without flattening their distinct commercial boundaries.
Counts sit with the page title, repeated directory headings and introductory
sentences are removed, and record names remain the collection entry point.
Services, invoices, and stock retain one visible create action when authorized;
the derived Vendors collection and MSP catalog chooser do not imply a second way
to create organization identity.

Product specification templates and recurring invoice schedules are supporting
working views, not permanent horizontal navigation or competing page actions.
Compact selectors expose them and preserve `catalog_view=templates` and
`invoice_view=recurring` in the URL. Opening a product or invoice returns to the
primary record view while keeping existing collection search, filter, order,
paging, drawer, record, and permission behavior unchanged. Issuance,
reauthentication, immutable invoice evidence, cost visibility, stock quantities,
and archive consequences retain their existing authorization and recovery
boundaries. This slice does not change backend APIs, persistence, or accounting
semantics.

Acceptance requires component coverage for all five Business destinations and
browser coverage across the six required widths for collections, drawers, direct
records, view selection, search, paging, recurring-invoice recovery, denial,
keyboard use, and accessibility.

## Assurance rollout

Compliance is the single Assurance destination. Its Frameworks, Evidence, Risks,
Review bundles, and Data flows are working views rather than permanent horizontal
navigation. A compact **Compliance view** selector preserves the existing
`section` query parameter and any unrelated query state. The active view exposes
one primary task in the page header: create a framework, add or link evidence,
record a risk, or create a locked review bundle. Data flows retains its contextual
declaration action because its permission and unavailable state are independently
enforced.

Repeated introductory copy is removed from the page and section headings. Guidance
remains where it changes a decision: new catalog versions retain history, accepted
risks identify the accepting person and stay in the register, locked bundles are
point-in-time records, and unverified data-flow drafts are explicitly not evidence.
Existing framework selection, stable control identities, evidence reuse and
linking, scored risk decisions, bundle verification, dirty-state recovery, direct
links, permissions, APIs, and persistence are unchanged.

Acceptance requires focused component coverage for all five views, retained query
state, canceled and confirmed unsaved-change navigation, immutable framework and
bundle behavior, evidence and risk decisions, and Data-flow provenance. Browser
coverage must confirm the compact hierarchy, accessibility, and lack of horizontal
overflow at all six required widths.

## Manage rollout

Manage contains three destinations: **Integrations**, **Data model**, and
**Recycle bin**. Settings remains in the permission-aware account menu until the
product has workspace-level settings rather than only personal and administrative
account controls.

Integrations uses one compact **Integration view** selector for Connections,
Imports, Review queue, Git exports, and Outgoing webhooks. Connections represent
configured external systems and their controlled synchronization. The Review
queue presents observed differences for an explicit operator decision; viewing a
difference does not silently change either record. Outgoing webhooks send selected
TekDocs events to an external endpoint and are therefore distinct from inbound or
bidirectional connections. Git exports remain sanitized transfer bundles, not a
backup. Existing `section` links, dirty-state protection, credentials,
reconciliation decisions, reviewed publication, and authorization remain intact.

Data model uses one compact **Data model view** selector for Fields and
**Categories and tags**. Fields add structured values to supported record types;
Categories and tags define controlled vocabularies for classifying supported
content. Organization workspaces expose only their applicable Fields view. The
existing custom-field and taxonomy paths, versioning, impact review, migration
preview, and permission boundaries remain unchanged.

Recycle bin removes repeated recovery copy and places its record count beside the
page title. Search, type filtering, paging, restore eligibility, missing-parent
handling, and the warning that restore is not backup remain unchanged. Across all
three destinations, the active view and count are stated once, collection search
stays visible, one create action is primary when applicable, and consequential
guidance stays adjacent to the decision it affects.

Acceptance requires component coverage for URL-backed view selection, lazy view
loading, create/edit recovery, reconciliation, version impact, migration preview,
restore success and failure, and loading/error/empty states. Browser coverage must
confirm retained query state, keyboard operation, accessibility, and responsive
layout at all six required widths. No API, schema, persistence, or authorization
change is part of this slice.

## Authentication and client portal rollout

Authentication remains a single restrained panel. Generic sign-in helper copy is
removed, while first-owner setup, MFA, recovery, invitation, error, and security
guidance remains available where it changes what the person must do.

The client portal presents the organization and a compact **Portal view** selector
for **Documents** and **Invoices**. Documents delivered through the legacy and
repository-backed publication paths appear in one date-ordered client list; their
storage and approval pipelines are not client navigation concepts. Existing
`section=publications` and `publication=` links remain valid for notifications,
saved links, refresh, and browser history. The separate authorization-checked APIs,
sanitized content, exact-client scoping, revocation behavior, retained downloads,
and invoice contract remain unchanged.

Acceptance covers sign-in, setup, MFA, reset, invitation, and sign-out; merged
document loading, pagination, partial failure, withdrawal, direct legacy links,
notifications, and invoices; and keyboard, refresh, history, zoom, responsive, and
accessibility behavior. This rollout does not change backend APIs, persistence,
database schema, or authorization.

## Repository action-hierarchy refinement

The repository editor is a contextual authoring workspace, not a second product
navigation layer. Its header keeps **Back to documentation** and one **New
Markdown file** primary action. Workspace-level source exports move to a plain
secondary menu. Saved-file downloads move beside the editor's save and close
controls in a separate export menu.

Export guidance appears with the export choices instead of occupying the page at
all times. It must still state the saved-revision boundary, possible live or
sensitive values, excluded unsaved edits, and the distinction from a backup or
STATIC publication. Git authority, conflict recovery, retained files, publishing,
permissions, download integrity, and direct repository links remain unchanged.

Acceptance covers menu keyboard operation, disabled and busy states, export
failure and revision-change recovery, dirty-draft preservation, direct links,
small-screen layout, zoom, and accessible names. No API, persistence, schema, or
authorization change is part of this refinement.

## Home reminder-agenda refinement

Home is the everyday workspace entry point, not an administrative dashboard.
The first-organization setup prompt remains conditional and disappears once an
organization exists. A shared reminder agenda appears on MSP Home and on any
organization Home authorized for reminders, with **New reminder** as the working
action and **View reminders** as the collection link. Creation opens the existing
workspace-scoped reminder form through its current query-preserving route.

Reminder loading and recovery are independent from setup detection and the rest
of the organization overview. A reminder denial or transient failure must not
hide setup, organization facts, provider tickets, or relationships. Activity
remains available through System status and existing direct links, but is not
reintroduced on Home. No API, persistence, authorization, or route change is
part of this refinement.

Acceptance covers conditional setup, MSP and organization reminder scope,
creation and collection links, empty/loading/error/retry states, capability
omission, keyboard access, 320–1440px layout, axe, and the existing Activity
deep-link contract.

## Reminder creation refinement

Reminder creation presents three essential choices first: **Related record**,
**Title**, and **Due date**. Area, advance notice, and recurrence move into a
plain **Options** disclosure. Selecting a supported record derives the matching
area while preserving an explicit override for the server-supported record
families. Unsupported record types are omitted from results instead of allowing
the user to reach a predictable server rejection.

The page retains one visible **New reminder** primary action. Calendar download
moves into a secondary **More** menu. Existing `new=1`, search, filtering,
ordering, paging, calendar, workspace scope, authorization, dirty-state,
creation-denial, and retry contracts remain unchanged. No backend API,
persistence, schema, or permission change is part of this refinement.

Acceptance covers supported-source filtering and area derivation, empty search,
advanced-option overrides, creation success and denial recovery, direct creation
links, unsaved-change protection, calendar access, keyboard operation, all six
review widths, zoom, axe, and untranslated-control coverage.

## November 15–17, 2026 implementation evidence

Verified:

- all 890 frontend unit/component tests pass with the repository coverage gates;
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
  shell; all 890 frontend unit/component tests, lint, type checking, and the
  production bundle gate remain green;
- 51 focused Chromium Business journeys pass across the required widths for
  services, vendors, products, invoices, recurring schedules, and stock. They
  include direct records, URL-backed supporting views, denial and recovery,
  keyboard use, 200% zoom, axe checks, and the reproduced narrow-header overflow;
  all 890 frontend unit/component tests and the production bundle gate remain
  green;
- ten focused Chromium Compliance and Data-flow journeys pass at 320, 390, 768,
  1024, 1280, and 1440px. They cover URL-backed view selection, unsaved-change
  recovery, accessible narrow-screen actions, retry behavior, keyboard authoring,
  permission omission, non-colour provenance, axe checks, and horizontal overflow;
  the rebuilt live Compliance page was also visually inspected;
- 29 focused Manage component tests and 41 focused Chromium browser journeys pass.
  They cover the Integration and Data model selectors, lazy loading, retry,
  unsaved-change recovery, reconciliation, custom-field and taxonomy workflows,
  Recycle bin, shell behavior, and all six required widths;
- all 890 frontend tests and 30 focused authentication and portal component tests
  pass for the final rollout. Twenty-four focused Chromium journeys cover sign-in,
  setup, MFA, sign-out, protected portal documents, withdrawal recovery, and the
  surrounding shell. Eight responsive Chromium/WebKit journeys cover the six
  required widths, 200% zoom, refresh, browser history, keyboard access, and axe;
- 45 repository component cases preserve export authorization, exact-revision
  downloads, conflict and failure recovery, and dirty drafts behind the revised
  action hierarchy. Four rebuilt-image Chromium journeys verify keyboard-operated
  export menus, contextual safety guidance, axe, and no horizontal overflow at
  320, 390, 768, and 1440px;
- all 893 frontend tests and 39 focused shell, authentication, and Home component
  cases pass with the shared reminder agenda. Six rebuilt-image Chromium journeys
  verify MSP and organization Home at 320, 390, 768, 1024, 1280, and 1440px,
  including keyboard entry to reminder creation, scoped links, axe, and overflow.
  Eight reminder/Activity journeys preserve creation, dirty-work recovery, direct
  Activity links, and all six widths; eight Chromium/WebKit responsive journeys
  preserve mobile and 200% zoom behavior;
- all 895 frontend tests pass with the repository coverage thresholds after the
  reminder-creation refinement. Nine rebuilt-image Chromium journeys cover the
  six required widths, supported record selection, inferred area, dirty-work
  recovery, keyboard operation, the 200% effective viewport, axe, calendar access,
  and horizontal overflow. Focused component cases additionally cover unsupported
  record omission, empty compatible search, search retry, creation denial, retained
  optional values, and successful recovery;
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
