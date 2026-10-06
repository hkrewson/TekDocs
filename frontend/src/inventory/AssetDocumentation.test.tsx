import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { InventoryClient } from './api'
import { AssetDocumentation } from './AssetDocumentation'

const workspace = { kind: 'organization', id: 'client-1', name: 'Client' } as never

describe('AssetDocumentation', () => {
  it('shows exact and model-wide documentation and opens sanitized content', async () => {
    const listContentDocumentation = vi.fn().mockResolvedValue({
      entity_id: 'asset-1', indexed_commit: 'a'.repeat(40),
      documents: [
        { id: 'doc-1', title: 'Laptop setup', kind: 'document', relationship: 'setup', scope: 'exact' },
        { id: 'doc-2', title: 'Model maintenance', kind: 'document', relationship: 'maintenance', scope: 'model' },
      ],
    })
    const readContentDocument = vi.fn().mockResolvedValue({
      id: 'doc-1', title: 'Laptop setup', kind: 'document', indexed_commit: 'a'.repeat(40),
      sanitized_html: '<p>Use the enrollment guide.</p>',
      entity_context: [{ id: 'asset-1', display_name: 'Renamed laptop', entity_type: 'client_asset', relationship: 'setup', origin: 'typed' }],
    })
    const client = { listContentDocumentation, readContentDocument } as unknown as InventoryClient
    const user = userEvent.setup()
    render(<AssetDocumentation workspace={workspace} assetId="asset-1" client={client} />)

    expect(await screen.findByText('Model maintenance')).toBeInTheDocument()
    expect(screen.getByText('This asset · Setup')).toBeInTheDocument()
    expect(screen.getByText('This model · Maintenance')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Laptop setup/ }))
    expect(await screen.findByText('Use the enrollment guide.')).toBeInTheDocument()
    expect(screen.getByText('Renamed laptop · Setup')).toBeInTheDocument()
    expect(listContentDocumentation).toHaveBeenCalledWith(workspace, 'asset-1', expect.any(AbortSignal))
    expect(readContentDocument).toHaveBeenCalledWith(workspace, 'doc-1', expect.any(AbortSignal))
  })

  it('keeps denied or failed reads inside a recoverable error state', async () => {
    const client = {
      listContentDocumentation: vi.fn().mockRejectedValue(new Error('Denied')),
      readContentDocument: vi.fn(),
    } as unknown as InventoryClient
    render(<AssetDocumentation workspace={workspace} assetId="asset-1" client={client} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Related documentation could not be loaded.')
  })
})
