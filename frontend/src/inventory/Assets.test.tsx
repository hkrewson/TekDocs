import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Assets } from './Assets'
import type { ClientAsset, InventoryClient } from './api'

const workspace = { id: 'client-1', name: 'Contoso', classifications: ['client'] } as never
const asset: ClientAsset = {
  id: 'asset-1', name: 'Core switch', kind: 'hardware', supplier_id: 'supplier-1', supplier_name: 'Northwind',
  product_id: 'product-1', product_name: 'EdgeSwitch', model_id: 'model-1', model_name: 'EdgeSwitch 24', model_number: 'ES-24',
  model_revision_id: 'revision-1', model_revision: 1, specification_version_id: 'version-1', specification_definition_id: 'definition-1', specification_version: 1,
  specifications: { ports: 24 }, provenance_checksum: 'a'.repeat(64), documents: [{
    publication_id: 'publication-1', source_document_id: 'document-1', title: 'Installation guide', category: 'guide', reason: 'Approved', content_digest: 'b'.repeat(64), published_at: '2026-08-10T12:00:00Z',
    verification: { valid: true, digest_valid: true, signature_valid: true, key_fingerprint_valid: true }, artifacts: [],
  }], created_at: '2026-08-10T12:00:00Z',
}

function inventoryClient(overrides: Partial<InventoryClient> = {}): InventoryClient {
  return {
    listAssets: vi.fn().mockResolvedValue({ results: [asset], count: 1, can_manage: true }),
    listModelChoices: vi.fn().mockResolvedValue({ results: [{ id: 'model-1', name: 'EdgeSwitch 24', model_number: 'ES-24', product_id: 'product-1', product_name: 'EdgeSwitch', kind: 'hardware', supplier_id: 'supplier-1', supplier_name: 'Northwind', revision: 1, specification_version_id: 'version-1', specifications: { ports: 24 } }] }),
    createAsset: vi.fn().mockResolvedValue(asset),
    loadDocument: vi.fn().mockResolvedValue({ ...asset.documents[0], sanitized_html: '<h1>Installation guide</h1>' }),
    listVendors: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    artifactUrl: vi.fn().mockReturnValue('/retained.pdf'),
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
    await user.click(screen.getByRole('button', { name: /Installation guide/ }))
    expect(await screen.findByText('Approved')).toBeInTheDocument()
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
})
