import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLocation } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { Licenses } from './Licenses'
import type { InventoryClient, SoftwareLicense } from './api'

const workspace = { kind: 'organization', id: 'client-1', name: 'Contoso', classifications: ['client'] } as never
const license: SoftwareLicense = {
  id: 'license-1', name: 'Endpoint protection', supplier_name: 'Northwind', product_id: 'product-1', product_name: 'Secure Agent', model_name: 'Business',
  kind: 'subscription', status: 'active', seat_limit: 25, active_seats: 0, starts_on: '2026-01-01', renews_on: '2027-01-01', ends_on: null,
  renewal_interval: 'annual', auto_renew: true, reference: 'AGR-100', installations: [{ id: 'installation-1', name: 'Reception Mac' }], seats: [],
  events: [{ id: 'event-1', event_type: 'created', installation_name: 'Reception Mac', person_name: null, seat_number: null, occurred_at: '2026-08-10T12:00:00Z' }],
}

function inventoryClient(overrides: Partial<InventoryClient> = {}): InventoryClient {
  return {
    listLicenses: vi.fn().mockResolvedValue({ results: [license], page: 1, page_size: 25, count: 1, has_more: false, can_manage: true }),
    retrieveLicense: vi.fn().mockResolvedValue(license),
    createLicense: vi.fn().mockResolvedValue(license), updateLicense: vi.fn().mockResolvedValue(license),
    softwareChoices: vi.fn().mockResolvedValue({ installations: [{ id: 'installation-1', asset_id: 'asset-1', asset_name: 'Reception Mac', product_id: 'product-1', product_name: 'Secure Agent', model_name: 'Business', status: 'installed', installed_version: '7.4', installed_on: '2026-08-01', last_verified_on: null, site_id: null, site_name: null }], people: [{ id: 'person-1', name: 'Morgan Ellis' }] }),
    linkLicenseInstallation: vi.fn().mockResolvedValue(license), assignLicenseSeat: vi.fn().mockResolvedValue({ ...license, active_seats: 1 }), revokeLicenseSeat: vi.fn().mockResolvedValue(license),
    ...overrides,
  } as unknown as InventoryClient
}

function Location() { return <output data-testid="location">{useLocation().search}</output> }
function renderLicenses(client: InventoryClient, initialPath = '/workspaces/organizations/client-1/licenses') {
  return render(<ApplicationRouter initialPath={initialPath}><Licenses workspace={workspace} client={client} /><Location /></ApplicationRouter>)
}

describe('Licenses', () => {
  it('creates a license from an exact software installation in the record drawer', async () => {
    const createLicense = vi.fn().mockResolvedValue(license)
    const user = userEvent.setup()
    renderLicenses(inventoryClient({ createLicense }))
    await user.click(await screen.findByRole('button', { name: 'New license' }))
    const drawer = within(screen.getByRole('dialog'))
    await user.type(drawer.getByLabelText('License name'), 'Endpoint protection')
    await user.selectOptions(drawer.getByLabelText('Initial software installation'), 'asset-1')
    await user.clear(drawer.getByLabelText('Seat limit'))
    await user.type(drawer.getByLabelText('Seat limit'), '25')
    await user.click(drawer.getByRole('button', { name: 'Create license' }))
    await waitFor(() => expect(createLicense).toHaveBeenCalledWith(workspace, expect.objectContaining({ name: 'Endpoint protection', asset_id: 'asset-1', seat_limit: 25, renewal_interval: 'annual' })))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('license=license-1'))
  })

  it('edits renewal state and assigns a retained seat from one license record', async () => {
    const updated = { ...license, renews_on: '2027-02-01' }
    const seated = { ...updated, active_seats: 1, seats: [{ id: 'seat-1', seat_number: 1, person_id: 'person-1', person_name: 'Morgan Ellis', installation_id: null, installation_name: null, assigned_at: '2026-08-10T13:00:00Z', revoked_at: null }] }
    const updateLicense = vi.fn().mockResolvedValue(updated)
    const assignLicenseSeat = vi.fn().mockResolvedValue(seated)
    const user = userEvent.setup()
    renderLicenses(inventoryClient({ updateLicense, assignLicenseSeat }))
    await user.click(await screen.findByRole('button', { name: 'Endpoint protection' }))
    await user.click(screen.getByRole('button', { name: 'Edit license' }))
    await user.clear(screen.getByLabelText('Renews on'))
    await user.type(screen.getByLabelText('Renews on'), '2027-02-01')
    await user.click(screen.getByRole('button', { name: 'Save license' }))
    await waitFor(() => expect(updateLicense).toHaveBeenCalledWith(workspace, 'license-1', expect.objectContaining({ renews_on: '2027-02-01', auto_renew: true })))
    await user.click(screen.getByRole('button', { name: 'Assign seat' }))
    await user.selectOptions(screen.getByLabelText('Person'), 'person-1')
    await user.click(screen.getByRole('button', { name: 'Assign seat' }))
    await waitFor(() => expect(assignLicenseSeat).toHaveBeenCalledWith(workspace, 'license-1', { person_id: 'person-1', installation_id: null }))
    expect(await screen.findByText('Morgan Ellis')).toBeInTheDocument()
  })

  it('restores collection controls and retrieves a license outside the current page', async () => {
    const listLicenses = vi.fn().mockResolvedValue({ results: [], page: 2, page_size: 25, count: 30, has_more: false, can_manage: true })
    const retrieveLicense = vi.fn().mockResolvedValue(license)
    renderLicenses(inventoryClient({ listLicenses, retrieveLicense }), '/workspaces/organizations/client-1/licenses?q=secure&license_kind=subscription&license_status=active&license_order=-renews_on&license_page=2&license=license-1')
    expect(await screen.findByRole('heading', { name: 'Endpoint protection' })).toBeInTheDocument()
    await waitFor(() => expect(listLicenses).toHaveBeenCalledWith(workspace, { q: 'secure', kind: 'subscription', status: 'active', ordering: '-renews_on', page: 2, page_size: 25 }, expect.any(AbortSignal)))
    expect(retrieveLicense).toHaveBeenCalledWith(workspace, 'license-1', expect.any(AbortSignal))
  })

  it('keeps a changed renewal form open until the user confirms discard', async () => {
    const user = userEvent.setup()
    renderLicenses(inventoryClient())
    await user.click(await screen.findByRole('button', { name: 'Endpoint protection' }))
    await user.click(screen.getByRole('button', { name: 'Edit license' }))
    await user.clear(screen.getByLabelText('Reference'))
    await user.type(screen.getByLabelText('Reference'), 'CHANGED')
    await user.click(screen.getByRole('link', { name: 'Back to licenses' }))
    expect(await screen.findByRole('heading', { name: 'Unsaved changes' })).toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'Endpoint protection' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Discard changes' }))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Endpoint protection' })).not.toBeInTheDocument())
  })
})
