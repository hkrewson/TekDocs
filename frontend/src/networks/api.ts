import { AuthRequestError, browserCsrfToken } from '../auth/api'
import type { WorkspaceContext } from '../workspaces/api'

export type NetworkRack = {
  id: string
  name: string
  site_id: string
  site_name: string
  location_id: string | null
  location_name: string | null
  unit_count: number
  status: 'planned' | 'active' | 'retired'
  device_count: number
}

export type NetworkDevice = {
  id: string
  name: string
  role: 'router' | 'switch' | 'firewall' | 'wireless_controller' | 'access_point' | 'load_balancer' | 'other'
  status: 'planned' | 'active' | 'offline' | 'retired'
  hardware_asset_id: string | null
  hardware_asset_name: string | null
  site_id: string | null
  site_name: string | null
  location_id: string | null
  location_name: string | null
  rack_id: string | null
  rack_name: string | null
  rack_unit: number | null
  rack_units: number
}

export type NetworkChoices = {
  sites: Array<{ id: string; name: string }>
  locations: Array<{ id: string; name: string; site_id: string }>
  racks: Array<{ id: string; name: string; site_id: string }>
  hardware_assets: Array<{ id: string; name: string }>
}

export type NetworkVRF = { id: string; name: string; route_distinguisher: string; description: string }
export type NetworkVLAN = { id: string; name: string; vlan_id: number; description: string }
export type NetworkSubnet = { id: string; name: string; cidr: string; address_family: 4 | 6; vrf_id: string | null; vrf_name: string | null; vlan_id: string | null; vlan_name: string | null; vlan_number: number | null; description: string }
export type VRFWrite = Omit<NetworkVRF, 'id'>
export type VLANWrite = Omit<NetworkVLAN, 'id'>
export type SubnetWrite = Pick<NetworkSubnet, 'name' | 'cidr' | 'description'> & { vrf_id: string | null; vlan_id: string | null }

export type RackWrite = Pick<NetworkRack, 'name' | 'unit_count' | 'status'> & { site_id: string; location_id: string | null }
export type DeviceWrite = Pick<NetworkDevice, 'name' | 'role' | 'status' | 'rack_units'> & {
  hardware_asset_id: string | null
  site_id: string | null
  location_id: string | null
  rack_id: string | null
  rack_unit: number | null
}

type ListResult<T> = { results: T[]; page: number; page_size: number; count: number; has_more: boolean; can_manage: boolean }
export type DeviceListResult = ListResult<NetworkDevice> & { can_view_relationships: boolean; can_create_relationships: boolean; can_archive_relationships: boolean }

export interface NetworksClient {
  listRacks(workspace: WorkspaceContext, signal?: AbortSignal): Promise<ListResult<NetworkRack>>
  createRack(workspace: WorkspaceContext, values: RackWrite): Promise<NetworkRack>
  updateRack(workspace: WorkspaceContext, rackId: string, values: RackWrite): Promise<NetworkRack>
  listDevices(workspace: WorkspaceContext, signal?: AbortSignal): Promise<DeviceListResult>
  createDevice(workspace: WorkspaceContext, values: DeviceWrite): Promise<NetworkDevice>
  updateDevice(workspace: WorkspaceContext, deviceId: string, values: DeviceWrite): Promise<NetworkDevice>
  choices(workspace: WorkspaceContext, signal?: AbortSignal): Promise<NetworkChoices>
  listVRFs(workspace: WorkspaceContext, signal?: AbortSignal): Promise<ListResult<NetworkVRF>>
  createVRF(workspace: WorkspaceContext, values: VRFWrite): Promise<NetworkVRF>
  updateVRF(workspace: WorkspaceContext, id: string, values: VRFWrite): Promise<NetworkVRF>
  listVLANs(workspace: WorkspaceContext, signal?: AbortSignal): Promise<ListResult<NetworkVLAN>>
  createVLAN(workspace: WorkspaceContext, values: VLANWrite): Promise<NetworkVLAN>
  updateVLAN(workspace: WorkspaceContext, id: string, values: VLANWrite): Promise<NetworkVLAN>
  listSubnets(workspace: WorkspaceContext, signal?: AbortSignal): Promise<ListResult<NetworkSubnet>>
  createSubnet(workspace: WorkspaceContext, values: SubnetWrite): Promise<NetworkSubnet>
  updateSubnet(workspace: WorkspaceContext, id: string, values: SubnetWrite): Promise<NetworkSubnet>
}

function basePath(workspace: WorkspaceContext) {
  return workspace.kind === 'organization'
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/networks`
    : '/api/v1/workspaces/msp/networks'
}

async function json<T>(response: Response): Promise<T> {
  let body: unknown
  try { body = await response.json() } catch { throw new AuthRequestError('The server returned an unreadable network response.', response.status) }
  if (!response.ok) {
    const detail = typeof body === 'object' && body && 'detail' in body ? String(body.detail) : 'The network request failed.'
    throw new AuthRequestError(detail, response.status)
  }
  return body as T
}

async function csrfToken() {
  let token = browserCsrfToken()
  if (!token) {
    await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    token = browserCsrfToken()
  }
  if (!token) throw new AuthRequestError('The browser security token is unavailable. Refresh and try again.')
  return token
}

async function write<T>(url: string, method: 'POST' | 'PATCH', values: unknown) {
  const response = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': await csrfToken() },
    body: JSON.stringify(values),
  })
  return json<T>(response)
}

export const browserNetworksClient: NetworksClient = {
  async listRacks(workspace, signal) {
    return json(await fetch(`${basePath(workspace)}/racks?page=1&page_size=100`, { credentials: 'same-origin', signal }))
  },
  createRack: (workspace, values) => write(`${basePath(workspace)}/racks`, 'POST', values),
  updateRack: (workspace, rackId, values) => write(`${basePath(workspace)}/racks/${encodeURIComponent(rackId)}`, 'PATCH', values),
  async listDevices(workspace, signal) {
    return json(await fetch(`${basePath(workspace)}/devices?page=1&page_size=100`, { credentials: 'same-origin', signal }))
  },
  createDevice: (workspace, values) => write(`${basePath(workspace)}/devices`, 'POST', values),
  updateDevice: (workspace, deviceId, values) => write(`${basePath(workspace)}/devices/${encodeURIComponent(deviceId)}`, 'PATCH', values),
  async choices(workspace, signal) {
    return json(await fetch(`${basePath(workspace)}/choices`, { credentials: 'same-origin', signal }))
  },
  async listVRFs(workspace, signal) {
    return json(await fetch(`${basePath(workspace)}/vrfs?page=1&page_size=100`, { credentials: 'same-origin', signal }))
  },
  createVRF: (workspace, values) => write(`${basePath(workspace)}/vrfs`, 'POST', values),
  updateVRF: (workspace, id, values) => write(`${basePath(workspace)}/vrfs/${encodeURIComponent(id)}`, 'PATCH', values),
  async listVLANs(workspace, signal) {
    return json(await fetch(`${basePath(workspace)}/vlans?page=1&page_size=100`, { credentials: 'same-origin', signal }))
  },
  createVLAN: (workspace, values) => write(`${basePath(workspace)}/vlans`, 'POST', values),
  updateVLAN: (workspace, id, values) => write(`${basePath(workspace)}/vlans/${encodeURIComponent(id)}`, 'PATCH', values),
  async listSubnets(workspace, signal) {
    return json(await fetch(`${basePath(workspace)}/subnets?page=1&page_size=100`, { credentials: 'same-origin', signal }))
  },
  createSubnet: (workspace, values) => write(`${basePath(workspace)}/subnets`, 'POST', values),
  updateSubnet: (workspace, id, values) => write(`${basePath(workspace)}/subnets/${encodeURIComponent(id)}`, 'PATCH', values),
}
