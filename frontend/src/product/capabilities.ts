import { translate } from '../i18n/localization'

export const capabilityRegistry = {
  overview: { label: translate('capability.overview'), path: '/overview', group: 'Workspace', status: 'supported', scopes: ['msp', 'organization'] },
  organizations: { label: translate('capability.organizations'), path: '/organizations', group: 'Workspace', status: 'supported', scopes: ['msp'] },
  people: { label: translate('capability.people'), path: '/people', group: 'Workspace', status: 'supported', scopes: ['msp', 'organization'] },
  sites: { label: translate('capability.sites'), path: '/sites', group: 'Workspace', status: 'supported', scopes: ['msp', 'organization'] },
  documentation: { label: translate('capability.documentation'), path: '/documentation', group: 'Workspace', status: 'supported', scopes: ['msp', 'organization'] },
  files: { label: translate('capability.files'), path: '/files', group: 'Workspace', status: 'supported', scopes: ['msp', 'organization'] },
  assets: { label: translate('capability.assets'), path: '/assets', group: 'Infrastructure', status: 'supported', scopes: ['msp', 'organization'] },
  licenses: { label: translate('capability.licenses'), path: '/licenses', group: 'Infrastructure', status: 'supported', scopes: ['msp', 'organization'] },
  networks: { label: translate('capability.networks'), path: '/networks', group: 'Infrastructure', status: 'supported', scopes: ['msp', 'organization'] },
  domains: { label: translate('capability.domains'), path: '/domains', group: 'Infrastructure', status: 'supported', scopes: ['msp', 'organization'] },
  certificates: { label: translate('capability.certificates'), path: '/certificates', group: 'Infrastructure', status: 'supported', scopes: ['msp', 'organization'] },
  credentials: { label: translate('capability.credentials'), path: '/credentials', group: 'Infrastructure', status: 'supported', scopes: ['msp', 'organization'] },
  services: { label: translate('capability.services'), path: '/services', group: 'Infrastructure', status: 'supported', scopes: ['msp', 'organization'] },
  vendors: { label: translate('capability.vendors'), path: '/vendors', group: 'Relationships', status: 'supported', scopes: ['msp', 'organization'] },
  products: { label: translate('capability.products'), path: '/products', group: 'Relationships', status: 'supported', scopes: ['msp', 'organization'] },
  invoices: { label: translate('capability.invoices'), path: '/invoices', group: 'Business', status: 'supported', scopes: ['msp', 'organization'] },
  stock: { label: translate('capability.stock'), path: '/stock', group: 'Business', status: 'supported', scopes: ['msp'] },
  custom_fields: { label: translate('capability.customFields'), path: '/custom-fields', group: 'Governance', status: 'supported', scopes: ['msp', 'organization'] },
  taxonomies: { label: translate('capability.taxonomies'), path: '/taxonomies', group: 'Governance', status: 'supported', scopes: ['msp'] },
  compliance: { label: translate('capability.compliance'), path: '/compliance', group: 'Governance', status: 'supported', scopes: ['msp', 'organization'] },
  deadlines: { label: translate('capability.reminders'), path: '/deadlines', group: 'Governance', status: 'supported', scopes: ['msp', 'organization'] },
  activity: { label: translate('capability.activity'), path: '/activity', group: 'Governance', status: 'supported', scopes: ['msp', 'organization'] },
  recycle_bin: { label: translate('capability.recycleBin'), path: '/recycle-bin', group: 'Governance', status: 'supported', scopes: ['msp', 'organization'] },
  integrations: { label: translate('capability.integrations'), path: '/integrations', group: 'Governance', status: 'supported', scopes: ['msp', 'organization'] },
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
