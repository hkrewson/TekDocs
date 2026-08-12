import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Licenses } from './Licenses'
import type { InventoryClient, SoftwareLicense } from './api'

const workspace = { id: 'client-1', name: 'Contoso', classifications: ['client'] } as never
const license: SoftwareLicense = {
  id: 'license-1', name: 'Endpoint protection', supplier_name: 'Northwind', product_id: 'product-1', product_name: 'Secure Agent', model_name: 'Business',
  kind: 'subscription', status: 'active', seat_limit: 25, active_seats: 0, starts_on: '2026-01-01', renews_on: '2027-01-01', ends_on: null,
  renewal_interval: 'annual', auto_renew: true, reference: 'AGR-100', installations: [{ id: 'installation-1', name: 'Reception Mac' }], seats: [],
  events: [{ id: 'event-1', event_type: 'created', installation_name: 'Reception Mac', person_name: null, seat_number: null, occurred_at: '2026-08-10T12:00:00Z' }],
}

function inventoryClient(overrides: Partial<InventoryClient> = {}): InventoryClient {
  return {
    listAssets: vi.fn(), listModelChoices: vi.fn(), createAsset: vi.fn(), bulkAssets: vi.fn(), updateHardware: vi.fn(), listHardwareLifecycle: vi.fn(), assignmentChoices: vi.fn(), assignHardware: vi.fn(), unassignHardware: vi.fn(), disposeHardware: vi.fn(), createAssetMACAddress: vi.fn(), updateAssetMACAddress: vi.fn(), updateSoftwareInstallation: vi.fn(),
    listLicenses: vi.fn().mockResolvedValue({ results: [license], page: 1, page_size: 50, count: 1, has_more: false, can_manage: true }),
    createLicense: vi.fn().mockResolvedValue(license), updateLicense: vi.fn().mockResolvedValue(license),
    softwareChoices: vi.fn().mockResolvedValue({ installations: [{ id: 'installation-1', asset_id: 'asset-1', asset_name: 'Reception Mac', product_id: 'product-1', product_name: 'Secure Agent', model_name: 'Business', status: 'installed', installed_version: '7.4', installed_on: '2026-08-01', last_verified_on: null, site_id: null, site_name: null }], people: [{ id: 'person-1', name: 'Morgan Ellis' }] }),
    linkLicenseInstallation: vi.fn().mockResolvedValue(license), assignLicenseSeat: vi.fn().mockResolvedValue({ ...license, active_seats: 1 }), revokeLicenseSeat: vi.fn().mockResolvedValue(license),
    loadDocument: vi.fn(), listVendors: vi.fn(), artifactUrl: vi.fn(), assetCsvTemplateUrl: vi.fn(), assetCsvExportUrl: vi.fn(), previewAssetCsv: vi.fn(), applyAssetCsv: vi.fn(),
    ...overrides,
  }
}

describe('Licenses', () => {
  it('creates a license from an exact software installation', async () => {
    const createLicense = vi.fn().mockResolvedValue(license)
    const user = userEvent.setup()
    render(<Licenses workspace={workspace} client={inventoryClient({ createLicense })} />)
    await user.click(await screen.findByRole('button', { name: 'New license' }))
    const form = screen.getByRole('heading', { name: 'New software license' }).closest('section')!
    await user.type(within(form).getByLabelText('License name'), 'Endpoint protection')
    await user.selectOptions(within(form).getByLabelText('Initial software installation'), 'asset-1')
    await user.clear(within(form).getByLabelText('Seat limit'))
    await user.type(within(form).getByLabelText('Seat limit'), '25')
    await user.click(within(form).getByRole('button', { name: 'Create license' }))
    await waitFor(() => expect(createLicense).toHaveBeenCalledWith(workspace, expect.objectContaining({ name: 'Endpoint protection', asset_id: 'asset-1', seat_limit: 25, renewal_interval: 'annual' })))
  })

  it('edits renewal state and assigns a retained seat', async () => {
    const updateLicense = vi.fn().mockResolvedValue({ ...license, renews_on: '2027-02-01' })
    const assignLicenseSeat = vi.fn().mockResolvedValue({ ...license, active_seats: 1, seats: [{ id: 'seat-1', seat_number: 1, person_id: 'person-1', person_name: 'Morgan Ellis', installation_id: null, installation_name: null, assigned_at: '2026-08-10T13:00:00Z', revoked_at: null }] })
    const user = userEvent.setup()
    render(<Licenses workspace={workspace} client={inventoryClient({ updateLicense, assignLicenseSeat })} />)
    await user.click(await screen.findByRole('button', { name: 'Edit license' }))
    const renewal = screen.getByLabelText('Renews on')
    await user.clear(renewal)
    await user.type(renewal, '2027-02-01')
    await user.click(screen.getByRole('button', { name: 'Save license' }))
    await waitFor(() => expect(updateLicense).toHaveBeenCalledWith(workspace, 'license-1', expect.objectContaining({ renews_on: '2027-02-01', auto_renew: true })))
    await user.click(screen.getByRole('button', { name: 'Assign seat' }))
    await user.selectOptions(screen.getByLabelText('Person'), 'person-1')
    await user.click(screen.getByRole('button', { name: 'Assign seat' }))
    await waitFor(() => expect(assignLicenseSeat).toHaveBeenCalledWith(workspace, 'license-1', { person_id: 'person-1', installation_id: null }))
    expect(await screen.findByText('Morgan Ellis')).toBeInTheDocument()
  })
})
