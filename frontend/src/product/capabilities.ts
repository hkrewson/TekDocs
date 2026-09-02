export const capabilityRegistry = {
  overview: { label: 'Overview', path: '/overview', group: 'Workspace', status: 'supported', scopes: ['msp', 'organization'] },
  organizations: { label: 'Organizations', path: '/organizations', group: 'Workspace', status: 'supported', scopes: ['msp'] },
  people: { label: 'People', path: '/people', group: 'Workspace', status: 'supported', scopes: ['msp', 'organization'] },
  sites: { label: 'Sites', path: '/sites', group: 'Workspace', status: 'supported', scopes: ['msp', 'organization'] },
  documentation: { label: 'Documentation', path: '/documentation', group: 'Workspace', status: 'supported', scopes: ['msp', 'organization'] },
  files: { label: 'Files', path: '/files', group: 'Workspace', status: 'supported', scopes: ['msp', 'organization'] },
  assets: { label: 'Assets', path: '/assets', group: 'Infrastructure', status: 'supported', scopes: ['msp', 'organization'] },
  licenses: { label: 'Licenses', path: '/licenses', group: 'Infrastructure', status: 'supported', scopes: ['msp', 'organization'] },
  networks: { label: 'Networks', path: '/networks', group: 'Infrastructure', status: 'supported', scopes: ['msp', 'organization'] },
  domains: { label: 'Domains', path: '/domains', group: 'Infrastructure', status: 'supported', scopes: ['msp', 'organization'] },
  certificates: { label: 'Certificates', path: '/certificates', group: 'Infrastructure', status: 'supported', scopes: ['msp', 'organization'] },
  credentials: { label: 'Credentials', path: '/credentials', group: 'Infrastructure', status: 'supported', scopes: ['msp', 'organization'] },
  services: { label: 'Services', path: '/services', group: 'Infrastructure', status: 'supported', scopes: ['msp', 'organization'] },
  vendors: { label: 'Vendors', path: '/vendors', group: 'Relationships', status: 'supported', scopes: ['msp', 'organization'] },
  products: { label: 'Products', path: '/products', group: 'Relationships', status: 'supported', scopes: ['msp', 'organization'] },
  invoices: { label: 'Invoices', path: '/invoices', group: 'Business', status: 'supported', scopes: ['msp', 'organization'] },
  custom_fields: { label: 'Custom fields', path: '/custom-fields', group: 'Governance', status: 'supported', scopes: ['msp', 'organization'] },
  taxonomies: { label: 'Taxonomies', path: '/taxonomies', group: 'Governance', status: 'supported', scopes: ['msp'] },
  compliance: { label: 'Compliance', path: '/compliance', group: 'Governance', status: 'supported', scopes: ['msp', 'organization'] },
  deadlines: { label: 'Reminders', path: '/deadlines', group: 'Governance', status: 'supported', scopes: ['msp', 'organization'] },
  activity: { label: 'Activity', path: '/activity', group: 'Governance', status: 'supported', scopes: ['msp', 'organization'] },
  recycle_bin: { label: 'Recycle bin', path: '/recycle-bin', group: 'Governance', status: 'supported', scopes: ['msp', 'organization'] },
  integrations: { label: 'Integrations', path: '/integrations', group: 'Governance', status: 'supported', scopes: ['msp', 'organization'] },
} as const

export type WorkspaceCapability = keyof typeof capabilityRegistry
export type CapabilityStatus = (typeof capabilityRegistry)[WorkspaceCapability]['status']
export type CapabilityGroup = (typeof capabilityRegistry)[WorkspaceCapability]['group']

export const workspaceCapabilities = Object.keys(capabilityRegistry) as WorkspaceCapability[]
export const supportedCapabilitySet = new Set<WorkspaceCapability>(workspaceCapabilities)

export function capabilityForPath(pathname: string): WorkspaceCapability | undefined {
  const path = `/${pathname.split('/').filter(Boolean)[0] ?? 'overview'}`
  return workspaceCapabilities.find((capability) => capabilityRegistry[capability].path === path)
}
