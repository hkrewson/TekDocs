import type { WorkspaceCapability, WorkspaceOption } from './api'
import { capabilityForPath, capabilityRegistry, workspaceCapabilities } from '../product/capabilities'

export type WorkspaceArea = WorkspaceCapability | 'settings' | 'search'

const recognizedAreas = new Set<WorkspaceArea>([...workspaceCapabilities, 'settings', 'search'])

export function workspaceAreaFromPath(pathname: string): WorkspaceArea {
  const segments = pathname.split('/').filter(Boolean)
  const candidate = segments[0] === 'workspaces' ? segments[3] : segments[0]
  if (candidate === 'accounting') return 'invoices'
  return recognizedAreas.has(candidate as WorkspaceArea) ? candidate as WorkspaceArea : 'overview'
}

export function mspWorkspacePath(area: WorkspaceArea): string {
  if (area === 'settings' || area === 'search') return `/${area}`
  return capabilityRegistry[area].path
}

export function organizationWorkspacePath(workspace: WorkspaceOption, area: WorkspaceArea): string {
  const selectedArea = area === 'search' || workspace.capabilities.includes(area as WorkspaceCapability) ? area : 'overview'
  return `/workspaces/organizations/${workspace.id}/${selectedArea}`
}

export { capabilityForPath }

export function classificationSummary(classifications: WorkspaceOption['classifications']): string {
  const labels = { client: 'Client', vendor: 'Vendor', manufacturer: 'Manufacturer', partner: 'Partner' }
  return classifications.map((classification) => labels[classification]).join(' · ')
}
