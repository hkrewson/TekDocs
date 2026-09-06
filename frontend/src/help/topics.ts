export type HelpTopic = {
  title: string
  summary: string
  slug: string
}

export const WIKI_BASE_URL = 'https://github.com/hkrewson/TekDocs/wiki'
export const WIKI_PUBLISHED = false

const topics: Record<string, HelpTopic> = {
  overview: { title: 'Workspace overview', summary: 'Understand MSP and organization ownership, navigation, and workspace boundaries.', slug: 'Workspaces-and-organizations' },
  search: { title: 'Workspace search', summary: 'Find documentation content and operational records inside the active workspace.', slug: 'Search' },
  organizations: { title: 'Organizations', summary: 'Create clients and suppliers, classify them, and enter their isolated workspaces.', slug: 'Organizations' },
  people: { title: 'People', summary: 'Manage MSP employees and organization contacts, locations, and access assignments.', slug: 'People-and-access' },
  sites: { title: 'Sites and locations', summary: 'Represent buildings and nested physical locations without mixing organization ownership.', slug: 'Sites-and-locations' },
  documentation: { title: 'Documentation', summary: 'Create Markdown-first documents, reuse live or pinned blocks, publish immutable STATIC copies, and assemble retained maps for runbooks and handoffs.', slug: 'Documentation' },
  taxonomies: { title: 'Controlled taxonomies', summary: 'Govern document terms, exact legacy-tag migration, aliases, hierarchy, retirement, and permitted client-local values.', slug: 'Documentation' },
  files: { title: 'Files and attachments', summary: 'Attach scanned, quarantined files to authorized records and retained publications.', slug: 'Files-and-attachments' },
  assets: { title: 'Assets', summary: 'Track hardware and software, supplier details, warranties, assignments, and costs.', slug: 'Assets' },
  licenses: { title: 'Software and licenses', summary: 'Track software installations, licenses, assigned seats, and renewals.', slug: 'Software-and-licenses' },
  networks: { title: 'Networks', summary: 'Document simple location-owned networks, VLANs, address ranges, gateways, and DNS.', slug: 'Networks' },
  domains: { title: 'Domains', summary: 'Record registrations, subdomains, renewal ownership, DNS results, and check history.', slug: 'Domains-and-certificates' },
  certificates: { title: 'Certificates', summary: 'Review TLS endpoints, validation results, expiration dates, and check history.', slug: 'Domains-and-certificates' },
  credentials: { title: 'Credential links', summary: 'Open credentials stored in 1Password without keeping passwords or secrets in TekDocs.', slug: 'Credential-references' },
  services: { title: 'Services and contracts', summary: 'Record suppliers, contracts, costs, renewals, and service dependencies.', slug: 'Services-and-contracts' },
  vendors: { title: 'Vendors and manufacturers', summary: 'See the organizations connected to assets and whether they sell, make, or both sell and make products.', slug: 'Vendors-and-products' },
  products: { title: 'Products and models', summary: 'Manage product lines, models, specification templates, saved versions, and documents included with new assets.', slug: 'Vendors-and-products' },
  custom_fields: { title: 'Custom fields', summary: 'Extend supported records with versioned, validated field definitions.', slug: 'Custom-fields' },
  compliance: { title: 'Compliance', summary: 'Track controls, evidence, risks, locked review bundles, and due dates.', slug: 'Compliance' },
  activity: { title: 'Activity', summary: 'See security and business changes made in this workspace.', slug: 'Audit-and-activity' },
  recycle_bin: { title: 'Recycle bin', summary: 'Restore archived records to this workspace.', slug: 'Recycle-bin' },
  integrations: { title: 'Integrations', summary: 'Preview safe imports, configure scoped webhooks and read-only synchronization, reconcile changes, and create sanitized exports.', slug: 'Integrations-and-API' },
  settings: { title: 'Account security', summary: 'Manage profile details, sessions, MFA, recovery codes, and API tokens.', slug: 'Account-security' },
  staff: { title: 'Staff and invitations', summary: 'Invite MSP staff, review invitation delivery and expiry, and continue into role and client assignment.', slug: 'People-and-access' },
  access_control: { title: 'Access control', summary: 'Assign built-in or custom roles at tenant, organization, and collection scope.', slug: 'Roles-and-permissions' },
  notification_delivery: { title: 'Notification delivery', summary: 'Inspect delivery state, retries, batching, digests, and mail-outage behavior.', slug: 'Notifications' },
  'system-status': { title: 'System status', summary: 'Check TekDocs, its database, and the isolated diagram renderer without exposing document content.', slug: 'Diagrams-in-documents' },
  invoices: { title: 'Invoices', summary: 'Build drafts from products, services, costs, or stock; issue locked invoices; email copies; and record payments or accounting updates.', slug: 'Invoices' },
  stock: { title: 'Stock', summary: 'Track MSP supplies, purchases, quantities, client use, costs, and stock used by invoice drafts.', slug: 'Stock' },
}

export function helpTopicForPath(pathname: string): HelpTopic {
  const workspaceMatch = pathname.match(/^\/workspaces\/organizations\/[^/]+\/([^/]+)/)
  const rawArea = workspaceMatch?.[1]
  const area = rawArea
    ? (rawArea === 'accounting' ? 'invoices' : rawArea.replaceAll('-', '_'))
    : pathname === '/accounting'
      ? 'invoices'
      : capabilityForPath(pathname) ?? pathname.split('/').filter(Boolean)[0] ?? 'overview'
  return topics[area] ?? topics.overview
}

export function helpTopicUrl(topic: HelpTopic) {
  return `${WIKI_BASE_URL}/${topic.slug}`
}

export const helpTopicSlugs = [...new Set(Object.values(topics).map((topic) => topic.slug))].sort()
import { capabilityForPath } from '../product/capabilities'
