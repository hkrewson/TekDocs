import type { WorkspaceCapability, WorkspaceOption } from './api'

export type WorkspaceArea = WorkspaceCapability | 'settings' | 'search'

const recognizedAreas = new Set<WorkspaceArea>([
  'overview',
  'documentation',
  'organizations',
  'people',
  'sites',
  'custom_fields',
  'files',
  'assets',
  'licenses',
  'networks',
  'domains',
  'certificates',
  'credentials',
  'services',
  'tickets',
  'vendors',
  'products',
  'compliance',
  'deadlines',
  'activity',
  'recycle_bin',
  'integrations',
  'accounting',
  'settings',
  'search',
])

const mspAreas = new Set<WorkspaceArea>([
  'overview',
  'documentation',
  'organizations',
  'people',
  'sites',
  'custom_fields',
  'files',
  'assets',
  'licenses',
  'networks',
  'domains',
  'certificates',
  'credentials',
  'services',
  'tickets',
  'vendors',
  'products',
  'compliance',
  'deadlines',
  'activity',
  'recycle_bin',
  'integrations',
  'accounting',
  'settings',
  'search',
])

export function workspaceAreaFromPath(pathname: string): WorkspaceArea {
  const segments = pathname.split('/').filter(Boolean)
  const candidate = segments[0] === 'workspaces' ? segments[3] : segments[0]
  return recognizedAreas.has(candidate as WorkspaceArea) ? candidate as WorkspaceArea : 'overview'
}

export function mspWorkspacePath(area: WorkspaceArea): string {
  return mspAreas.has(area) ? `/${area}` : '/overview'
}

export function organizationWorkspacePath(workspace: WorkspaceOption, area: WorkspaceArea): string {
  const selectedArea = area === 'search' || workspace.capabilities.includes(area as WorkspaceCapability) ? area : 'overview'
  return `/workspaces/organizations/${workspace.id}/${selectedArea}`
}

export function classificationSummary(classifications: WorkspaceOption['classifications']): string {
  const labels = { client: 'Client', vendor: 'Vendor', manufacturer: 'Manufacturer', partner: 'Partner' }
  return classifications.map((classification) => labels[classification]).join(' · ')
}
