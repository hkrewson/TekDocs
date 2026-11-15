# Post-1.0 interface rework

Status: reference slice implemented and automated validation complete; maintainer acceptance pending.

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
| Home | Overview, Reminders, Activity |
| Clients | Organizations, People, Sites |
| Knowledge | Documentation, Files |
| Operations | Assets, Licenses, Networks, Domains, Certificates, Credentials |
| Business | Services, Vendors, Products, Invoices, Stock |
| Assurance | Compliance, Recycle bin |
| Manage | Integrations, Custom fields, Taxonomies |

Personal settings, staff, access control, notification delivery, and system
status remain in the permission-aware account menu. Workspace capabilities and
permissions remain the source of truth. Omitting a link is not an authorization
decision; the server continues to enforce every request.

Desktop uses a solid 244px sidebar and a plain local navigation row. At 800px
and below the sidebar remains a focus-trapped overlay and the local navigation
becomes a labeled section selector. Existing workspace switching, global search,
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
| Home | `/deadlines` | `deadlines` capability | review reminders |
| Home | `/activity` | `activity` capability | review activity |
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
| Assurance | `/recycle-bin` | `recycle_bin` capability | restore eligible record |
| Manage | `/integrations` | `integrations` capability | add or inspect integration |
| Manage | `/custom-fields` | `custom_fields` capability | new custom field |
| Manage | `/taxonomies` | MSP `taxonomies` capability | new taxonomy |

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

Documentation has four stable local views: **Documents**, **Templates**,
**Repository**, and **Content health**. Search stays visible, filters remain in
the shared filter menu, and **New document** is the single primary collection
action. Import and repository work are subordinate. A selected document exposes
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

## November 15, 2026 implementation evidence

Verified:

- all 886 frontend unit/component tests pass with the repository coverage gates;
- lint, type checking, generated API agreement, the production build, CSP checks,
  untranslated-control coverage, and bundle budgets pass;
- 60 reference shell/document browser cases pass across the six required widths,
  including Git-backed document and publication recovery paths;
- eight Chromium/WebKit responsive cases pass across the required widths and
  200% zoom, including mobile navigation focus behavior;
- the rebuilt frontend and backend are healthy in the existing `tekdocs`
  Compose project; no parallel project or data volume is in use;
- the retained development tenant preserves its existing owner and now contains
  three verified acceptance workspaces; each has 31 mixed assets, 30 contracts,
  30 networks, 30 Git-backed documents, one fragment, and 32 checksum-verified
  managed files, plus limited users and a retained client publication;
- the public Wiki checkout passes all 37 required pages and 55 total pages.

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
