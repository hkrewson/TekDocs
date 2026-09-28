import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { defaultPreferences } from '../collections/preferences'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworksClient } from './api'
import { DeviceRegister } from './DeviceRegister'

const workspace = { kind: 'msp', id: 'msp', name: 'MSP' } as WorkspaceContext
const record = {
  id: 'device-1', name: 'Core switch', role: 'switch', status: 'active', hardware_asset_id: 'asset-1', hardware_asset_name: 'Core switch',
  site_id: 'site-1', site_name: 'Campus', location_id: null, location_name: null, rack_id: 'rack-1', rack_name: 'Core rack',
  rack_unit: 2, rack_units: 1, netbox_id: 417, serial_number: 'SW-000417', manufacturer_name: 'Arista', product_name: 'Campus switch',
  model_name: '7050SX3', source_observed_at: '2026-09-28T12:00:00Z',
}
function setup(initialPath = '/networks?view=devices') {
  window.history.replaceState({}, '', initialPath)
  const deviceCollection = vi.fn().mockResolvedValue({ results: [record], count: 1, page: 1, page_size: 25, has_more: false, can_manage: true, can_create: true })
  const client = { deviceCollection, deviceDetail: vi.fn().mockResolvedValue(record) } as unknown as NetworksClient
  const preferences = defaultPreferences(['name', 'netbox_id', 'rack', 'rack_unit', 'rack_units', 'serial_number', 'model_name'])
  const preferenceClient = { load: vi.fn().mockResolvedValue(preferences), save: vi.fn().mockResolvedValue(preferences), reset: vi.fn().mockResolvedValue(preferences) }
  render(<ApplicationRouter><DeviceRegister workspace={workspace} client={client} preferenceClient={preferenceClient} /></ApplicationRouter>)
  return { deviceCollection, user: userEvent.setup() }
}

it('shows the supported NetBox and asset facts without standalone authoring controls', async () => {
  const { user } = setup()
  await user.click(await screen.findByRole('button', { name: 'Core switch' }))
  const drawer = await screen.findByRole('dialog', { name: 'Core switch' })
  expect(within(drawer).getByText('417')).toBeInTheDocument()
  expect(within(drawer).getByText('Core rack')).toBeInTheDocument()
  expect(within(drawer).getByText('SW-000417')).toBeInTheDocument()
  expect(within(drawer).getByText('Arista')).toBeInTheDocument()
  expect(within(drawer).getByText('Campus switch')).toBeInTheDocument()
  expect(within(drawer).getByText('7050SX3')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'New device' })).not.toBeInTheDocument()
  expect(within(drawer).queryByRole('button', { name: /Edit/ })).not.toBeInTheDocument()
  expect(within(drawer).queryByRole('link', { name: 'Placement' })).not.toBeInTheDocument()
  expect(within(drawer).queryByRole('link', { name: 'Interfaces' })).not.toBeInTheDocument()
  fireEvent(drawer, new Event('cancel', { cancelable: true }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})

it('searches the complete device projection and keeps history as evidence', async () => {
  const { user, deviceCollection } = setup()
  fireEvent.change(await screen.findByRole('searchbox', { name: 'Search devices' }), { target: { value: 'SW-000417' } })
  await user.click(screen.getByRole('button', { name: 'Search' }))
  await waitFor(() => expect(deviceCollection).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ q: 'SW-000417', page: 1, page_size: 25, ordering: 'name' }), expect.any(AbortSignal)))
  await user.click(screen.getByRole('button', { name: 'Core switch' }))
  const drawer = await screen.findByRole('dialog', { name: 'Core switch' })
  await user.click(within(drawer).getByRole('link', { name: 'History' }))
  expect(window.location.search).toContain('devices_section=history')
})

it('opens a direct device record with only overview and history sections', async () => {
  setup('/networks?view=devices&devices=device-1&devices_section=placement')
  const drawer = await screen.findByRole('dialog', { name: 'Core switch' })
  expect(within(drawer).getByRole('link', { name: 'Overview' })).toHaveAttribute('aria-current', 'page')
  expect(within(drawer).getAllByRole('link').map((link) => link.textContent)).toEqual(expect.arrayContaining(['Open in full page', 'Overview', 'History']))
})
