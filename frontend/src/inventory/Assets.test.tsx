import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Assets } from './Assets'
import type { HardwareLifecycleEvent } from './api'
import type { ClientAsset, InventoryClient } from './api'

const workspace = { id: 'client-1', name: 'Contoso', classifications: ['client'] } as never
const asset: ClientAsset = {
  id: 'asset-1', name: 'Core switch', kind: 'hardware', supplier_id: 'supplier-1', supplier_name: 'Northwind',
  product_id: 'product-1', product_name: 'EdgeSwitch', model_id: 'model-1', model_name: 'EdgeSwitch 24', model_number: 'ES-24',
  model_revision_id: 'revision-1', model_revision: 1, specification_version_id: 'version-1', specification_definition_id: 'definition-1', specification_version: 1,
  specifications: { ports: 24 }, provenance_checksum: 'a'.repeat(64), documents: [{
    publication_id: 'publication-1', source_document_id: 'document-1', title: 'Installation guide', category: 'guide', reason: 'Approved', content_digest: 'b'.repeat(64), published_at: '2026-08-10T12:00:00Z',
    verification: { valid: true, digest_valid: true, signature_valid: true, key_fingerprint_valid: true }, artifacts: [],
  }], hardware: {
    serial_number: 'SN-001', asset_tag: 'SW-001', lifecycle_state: 'in_service', acquired_on: '2026-08-01', acquisition_method: 'purchase', acquisition_reference: '',
    warranty_provider: 'Northwind', warranty_starts_on: '2026-08-01', warranty_ends_on: '2029-08-01', warranty_reference: '',
    assignment: { person_id: null, person_name: null, site_id: null, site_name: null, location_id: null, location_name: null, assigned_at: null },
    disposed_on: null, disposal_method: '', disposal_reason: '',
  }, mac_addresses: [], software_installation: null, created_at: '2026-08-10T12:00:00Z',
}
const softwareAsset: ClientAsset = {
  ...asset,
  id: 'software-asset-1',
  name: 'Reception endpoint protection',
  kind: 'software',
  product_name: 'Secure Agent',
  model_name: 'Business',
  model_number: 'SEC-BIZ',
  documents: [],
  hardware: null,
  software_installation: {
    id: 'installation-1', status: 'planned', installed_version: '', installed_on: null,
    last_verified_on: null, site_id: null, site_name: null,
  },
}

function inventoryClient(overrides: Partial<InventoryClient> = {}): InventoryClient {
  return {
    listAssets: vi.fn().mockResolvedValue({ results: [asset], page: 1, page_size: 50, count: 1, has_more: false, can_manage: true, can_view_relationships: false, can_create_relationships: false, can_archive_relationships: false }),
    listModelChoices: vi.fn().mockResolvedValue({ results: [{ id: 'model-1', name: 'EdgeSwitch 24', model_number: 'ES-24', product_id: 'product-1', product_name: 'EdgeSwitch', kind: 'hardware', supplier_id: 'supplier-1', supplier_name: 'Northwind', revision: 1, specification_version_id: 'version-1', specifications: { ports: 24 } }] }),
    createAsset: vi.fn().mockResolvedValue(asset),
    bulkAssets: vi.fn().mockResolvedValue({ action: 'set_hardware_state', processed: 1 }),
    updateHardware: vi.fn().mockResolvedValue(asset.hardware),
    listHardwareLifecycle: vi.fn().mockResolvedValue([{ id: 'event-1', event_type: 'created', from_state: '', to_state: 'in_stock', person_name: null, site_name: null, location_name: null, occurred_at: '2026-08-10T12:00:00Z' }]),
    assignmentChoices: vi.fn().mockResolvedValue({ people: [], sites: [], locations: [] }),
    assignHardware: vi.fn().mockResolvedValue(asset.hardware),
    unassignHardware: vi.fn().mockResolvedValue(asset.hardware),
    disposeHardware: vi.fn().mockResolvedValue(asset.hardware),
    createAssetMACAddress: vi.fn(),
    updateAssetMACAddress: vi.fn(),
    updateSoftwareInstallation: vi.fn(),
    listLicenses: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 50, count: 0, has_more: false, can_manage: true }),
    createLicense: vi.fn(),
    updateLicense: vi.fn(),
    softwareChoices: vi.fn().mockResolvedValue({ installations: [], people: [] }),
    linkLicenseInstallation: vi.fn(),
    assignLicenseSeat: vi.fn(),
    revokeLicenseSeat: vi.fn(),
    loadDocument: vi.fn().mockResolvedValue({ ...asset.documents[0], sanitized_html: '<h1>Installation guide</h1>' }),
    listVendors: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    artifactUrl: vi.fn().mockReturnValue('/retained.pdf'),
    assetCsvTemplateUrl: vi.fn().mockReturnValue('/assets-template.csv'),
    assetCsvExportUrl: vi.fn().mockReturnValue('/assets.csv'),
    previewAssetCsv: vi.fn(),
    applyAssetCsv: vi.fn(),
    ...overrides,
  }
}

describe('Assets', () => {
  it('shows retained catalog and STATIC publication provenance', async () => {
    const user = userEvent.setup()
    render(<Assets workspace={workspace} client={inventoryClient()} />)
    expect(await screen.findByRole('heading', { name: 'Core switch' })).toBeInTheDocument()
    expect(screen.getByText('Northwind / EdgeSwitch / EdgeSwitch 24')).toBeInTheDocument()
    expect(screen.getByText('24')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Hardware lifecycle' })).toBeInTheDocument()
    expect(screen.getByText('SN-001')).toBeInTheDocument()
    expect(await screen.findByText('created')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Installation guide/ }))
    expect(await screen.findByText('Approved')).toBeInTheDocument()
  })

  it('records MAC addresses on the physical asset instead of the Networks page', async () => {
    const created = { id: 'mac-1', address: '02:00:00:00:00:01', description: 'Ethernet' }
    const createAssetMACAddress = vi.fn().mockResolvedValue(created)
    const user = userEvent.setup()
    render(<Assets workspace={workspace} client={inventoryClient({ createAssetMACAddress })} />)
    expect(await screen.findByRole('heading', { name: 'MAC addresses' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add address' }))
    await user.type(screen.getByLabelText('MAC address'), created.address)
    await user.type(screen.getByLabelText('Description'), created.description)
    await user.click(screen.getByRole('button', { name: 'Save address' }))
    await waitFor(() => expect(createAssetMACAddress).toHaveBeenCalledWith(workspace, 'asset-1', {
      address: created.address,
      description: created.description,
    }))
    expect(await screen.findByText(created.address)).toBeInTheDocument()
  })

  it('requires a reviewed dry run before applying an asset CSV', async () => {
    const user = userEvent.setup()
    const previewAssetCsv = vi.fn().mockResolvedValue({
      schema_version: 'tekdocs.assets.v1',
      rows: [{ row: 2, asset_id: 'asset-2', name: 'Imported switch', kind: 'hardware', action: 'create', changes: ['asset'] }],
      errors: [], summary: { total: 1, create: 1, update: 0, skip: 0, errors: 0 }, preview_token: 'signed-preview',
    })
    const applyAssetCsv = vi.fn().mockResolvedValue({ created: 1, updated: 0, skipped: 0 })
    render(<Assets workspace={workspace} client={inventoryClient({ previewAssetCsv, applyAssetCsv })} />)
    await user.click(await screen.findByRole('button', { name: 'Import CSV' }))
    const file = new File(['schema_version\ntekdocs.assets.v1\n'], 'assets.csv', { type: 'text/csv' })
    await user.upload(screen.getByLabelText('TekDocs asset CSV'), file)
    await user.click(screen.getByRole('button', { name: 'Preview changes' }))
    expect(await screen.findByText('Imported switch')).toBeInTheDocument()
    expect(previewAssetCsv).toHaveBeenCalledWith(workspace, file)
    await user.click(screen.getByRole('button', { name: 'Apply import' }))
    await waitFor(() => expect(applyAssetCsv).toHaveBeenCalledWith(workspace, file, 'signed-preview'))
    expect(await screen.findByText('1 created, 0 updated, 0 unchanged.')).toBeInTheDocument()
  })

  it('creates an asset from an exact supplier model', async () => {
    const createAsset = vi.fn().mockResolvedValue({ ...asset, id: 'asset-2', name: 'Reception switch' })
    const user = userEvent.setup()
    render(<Assets workspace={workspace} client={inventoryClient({ createAsset })} />)
    await user.click(await screen.findByRole('button', { name: 'New asset' }))
    const form = screen.getByRole('heading', { name: 'New asset from supplier model' }).closest('section')!
    await waitFor(() => expect(within(form).getByRole('option', { name: /Northwind/ })).toBeInTheDocument())
    await user.selectOptions(within(form).getByLabelText('Supplier model'), 'model-1')
    await user.type(within(form).getByLabelText('Asset name (optional)'), 'Reception switch')
    await user.click(within(form).getByRole('button', { name: 'Create asset' }))
    await waitFor(() => expect(createAsset).toHaveBeenCalledWith(workspace, 'model-1', 'Reception switch'))
  })

  it('applies a bounded bulk hardware state change', async () => {
    const bulkAssets = vi.fn().mockResolvedValue({ action: 'set_hardware_state', processed: 1 })
    const user = userEvent.setup()
    render(<Assets workspace={workspace} client={inventoryClient({ bulkAssets })} />)
    await user.click(await screen.findByRole('checkbox', { name: 'Select Core switch' }))
    await user.selectOptions(screen.getByLabelText('State'), 'repair')
    await user.click(screen.getByRole('button', { name: 'Apply' }))
    await waitFor(() => expect(bulkAssets).toHaveBeenCalledWith(workspace, ['asset-1'], 'set_hardware_state', 'repair'))
  })

  it('requires explicit confirmation before bulk archiving', async () => {
    const bulkAssets = vi.fn().mockResolvedValue({ action: 'archive', processed: 1 })
    const user = userEvent.setup()
    render(<Assets workspace={workspace} client={inventoryClient({ bulkAssets })} />)
    await user.click(await screen.findByRole('checkbox', { name: 'Select Core switch' }))
    await user.selectOptions(screen.getByLabelText('Action'), 'archive')
    await user.click(screen.getByRole('button', { name: 'Review archive' }))
    expect(bulkAssets).not.toHaveBeenCalled()
    expect(screen.getByRole('status')).toHaveTextContent('Archive 1 selected assets?')
    await user.click(screen.getByRole('button', { name: 'Confirm archive' }))
    await waitFor(() => expect(bulkAssets).toHaveBeenCalledWith(workspace, ['asset-1'], 'archive', undefined))
  })

  it('edits hardware identity through the lifecycle service', async () => {
    const updateHardware = vi.fn().mockResolvedValue({ ...asset.hardware!, serial_number: 'SN-002' })
    const user = userEvent.setup()
    render(<Assets workspace={workspace} client={inventoryClient({ updateHardware })} />)
    await user.click(await screen.findByRole('button', { name: 'Edit details' }))
    const serial = screen.getByLabelText('Serial number')
    await user.clear(serial)
    await user.type(serial, 'SN-002')
    await user.click(screen.getByRole('button', { name: 'Save details' }))
    await waitFor(() => expect(updateHardware).toHaveBeenCalledWith(
      workspace,
      'asset-1',
      expect.objectContaining({ serial_number: 'SN-002', lifecycle_state: 'in_service' }),
    ))
  })

  // A slow history load must not discard what is being typed.
  it('keeps an open hardware edit when a background history refresh lands', async () => {
    let releaseHistory: (events: HardwareLifecycleEvent[]) => void = () => {}
    const listHardwareLifecycle = vi.fn(
      () => new Promise<HardwareLifecycleEvent[]>((resolve) => { releaseHistory = resolve }),
    )
    const user = userEvent.setup()
    render(<Assets workspace={workspace} client={inventoryClient({ listHardwareLifecycle })} />)

    await user.click(await screen.findByRole('button', { name: 'Edit details' }))
    await user.clear(screen.getByLabelText('Serial number'))
    await user.type(screen.getByLabelText('Serial number'), 'SN-IN-PROGRESS')

    // The history request that was already in flight now resolves. Before this was
    // fixed it also reset the form and forced read mode, so a half-typed serial
    // vanished and the rest of the form went with it.
    await act(() => { releaseHistory([]); return Promise.resolve() })

    expect(screen.getByLabelText('Serial number')).toHaveValue('SN-IN-PROGRESS')
    expect(screen.getByLabelText('Acquired on')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save details' })).toBeInTheDocument()
  })

  it('maintains software installation status and version', async () => {
    const updated = { ...softwareAsset.software_installation!, status: 'installed' as const, installed_version: '7.4.1', installed_on: '2026-08-10' }
    const updateSoftwareInstallation = vi.fn().mockResolvedValue(updated)
    const user = userEvent.setup()
    render(<Assets workspace={workspace} client={inventoryClient({
      listAssets: vi.fn().mockResolvedValue({ results: [softwareAsset], page: 1, page_size: 50, count: 1, has_more: false, can_manage: true, can_view_relationships: false, can_create_relationships: false, can_archive_relationships: false }),
      updateSoftwareInstallation,
    })} />)
    expect(await screen.findByRole('heading', { name: 'Software installation' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Edit installation' }))
    await user.selectOptions(screen.getByLabelText('Status'), 'installed')
    await user.type(screen.getByLabelText('Installed version'), '7.4.1')
    await user.type(screen.getByLabelText('Installed on'), '2026-08-10')
    await user.click(screen.getByRole('button', { name: 'Save installation' }))
    await waitFor(() => expect(updateSoftwareInstallation).toHaveBeenCalledWith(workspace, 'software-asset-1', expect.objectContaining({ status: 'installed', installed_version: '7.4.1', installed_on: '2026-08-10' })))
    expect(await screen.findByText('7.4.1')).toBeInTheDocument()
  })
})
