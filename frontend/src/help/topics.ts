export type HelpTopic = {
  title: string
  summary: string
  slug: string
}

export const WIKI_BASE_URL = 'https://github.com/hkrewson/TekDocs/wiki'
export const WIKI_PUBLISHED = false

const topics: Record<string, HelpTopic> = {
  overview: { title: 'Workspace overview', summary: 'Understand MSP and organization ownership, navigation, and workspace boundaries.', slug: 'Workspaces-and-organizations' },
  search: { title: 'Workspace search', summary: 'Find records through the active workspace and its permission boundary.', slug: 'Workspaces-and-organizations' },
  organizations: { title: 'Organizations', summary: 'Create clients and suppliers, classify them, and enter their isolated workspaces.', slug: 'Organizations' },
  people: { title: 'People', summary: 'Manage MSP employees and organization contacts, locations, and access assignments.', slug: 'People-and-access' },
  sites: { title: 'Sites and locations', summary: 'Represent buildings and nested physical locations without mixing organization ownership.', slug: 'Sites-and-locations' },
  documentation: { title: 'Documentation', summary: 'Create Markdown-first documents, reuse live or pinned blocks, and publish immutable STATIC copies.', slug: 'Documentation' },
  files: { title: 'Files and attachments', summary: 'Attach scanned, quarantined files to authorized records and retained publications.', slug: 'Files-and-attachments' },
  assets: { title: 'Assets', summary: 'Track physical assets, supplier provenance, lifecycle, warranties, assignments, and permitted costs.', slug: 'Assets' },
  licenses: { title: 'Software and licenses', summary: 'Track software installations, entitlements, seats, assignments, and renewals.', slug: 'Software-and-licenses' },
  networks: { title: 'Networks', summary: 'Document simple location-owned networks, VLANs, address ranges, gateways, and DNS.', slug: 'Networks' },
  domains: { title: 'Domains', summary: 'Record registrations, subdomains, renewal ownership, DNS observations, and monitoring.', slug: 'Domains-and-certificates' },
  certificates: { title: 'Certificates', summary: 'Review TLS endpoint observations, chain validity, expiry state, and monitoring history.', slug: 'Domains-and-certificates' },
  credentials: { title: 'Credential references', summary: 'Link to externally protected 1Password items without storing secret values in TekDocs.', slug: 'Credential-references' },
  services: { title: 'Services and contracts', summary: 'Document providers, contracts, costs, renewals, and operational dependencies.', slug: 'Services-and-contracts' },
  vendors: { title: 'Vendors', summary: 'Review suppliers derived from products, assets, services, and organization relationships.', slug: 'Vendors-and-products' },
  products: { title: 'Products and models', summary: 'Maintain supplier catalogs and versioned specifications that retain provenance in client assets.', slug: 'Vendors-and-products' },
  custom_fields: { title: 'Custom fields', summary: 'Extend supported records with versioned, validated field definitions.', slug: 'Custom-fields' },
  compliance: { title: 'Compliance', summary: 'Manage framework assignments, evidence, risks, signed bundles, and review reminders.', slug: 'Compliance' },
  activity: { title: 'Activity and audit evidence', summary: 'Review permission-aware, append-only security and business events.', slug: 'Audit-and-activity' },
  recycle_bin: { title: 'Recycle bin', summary: 'Recover archived records through the same workspace and authorization boundaries.', slug: 'Recycle-bin' },
  integrations: { title: 'Integrations', summary: 'Configure scoped tokens, webhooks, read-only synchronization, reconciliation, and exports.', slug: 'Integrations-and-API' },
  settings: { title: 'Account security', summary: 'Manage profile details, sessions, MFA, recovery codes, and API tokens.', slug: 'Account-security' },
  staff: { title: 'Staff and invitations', summary: 'Invite MSP staff, review invitation delivery and expiry, and continue into role and client assignment.', slug: 'People-and-access' },
  access_control: { title: 'Access control', summary: 'Assign built-in or custom roles at tenant, organization, and collection scope.', slug: 'Roles-and-permissions' },
  notification_delivery: { title: 'Notification delivery', summary: 'Inspect delivery state, retries, batching, digests, and mail-outage behavior.', slug: 'Notifications' },
  tickets: { title: 'Tickets', summary: 'Understand the planned service-request boundary for a future release.', slug: 'Product-boundaries' },
  accounting: { title: 'Invoice drafts', summary: 'Create unnumbered invoice drafts with fixed line descriptions, prices, currencies, and tax values.', slug: 'Invoice-drafts' },
}

export function helpTopicForPath(pathname: string): HelpTopic {
  const workspaceMatch = pathname.match(/^\/workspaces\/organizations\/[^/]+\/([^/]+)/)
  const area = (workspaceMatch?.[1] ?? pathname.split('/').filter(Boolean)[0] ?? 'overview').replaceAll('-', '_')
  return topics[area] ?? topics.overview
}

export function helpTopicUrl(topic: HelpTopic) {
  return `${WIKI_BASE_URL}/${topic.slug}`
}

export const helpTopicSlugs = [...new Set(Object.values(topics).map((topic) => topic.slug))].sort()
