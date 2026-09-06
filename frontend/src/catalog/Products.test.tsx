import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Products } from './Products'
import type { CatalogClient, CatalogProduct, SpecificationDefinition } from './api'

const workspace = { id: 'supplier-1', name: 'Northwind Supply', classifications: ['vendor'] } as never
const definition: SpecificationDefinition = {
  id: 'definition-1',
  name: 'Managed switch',
  product_kind: 'hardware',
  versions: [{
    id: 'version-1',
    version: 1,
    schema: {
      type: 'object',
      additionalProperties: false,
      properties: { ports: { type: 'integer', title: 'Port count' }, managed: { type: 'boolean', title: 'Managed' } },
      required: ['ports'],
    },
    checksum: 'a'.repeat(64),
    created_by: 'Catalog Owner',
    created_at: '2026-08-09T12:00:00Z',
  }],
}
const product: CatalogProduct = {
  id: 'product-1',
  name: 'EdgeSwitch',
  kind: 'hardware',
  description: 'Managed switching family',
  updated_at: '2026-08-09T12:00:00Z',
  documents: [],
  models: [{
    id: 'model-1',
    name: 'EdgeSwitch 24',
    model_number: 'ES-24',
    current_revision: {
      id: 'revision-1', revision: 1, parent_id: null, specification_version_id: 'version-1', specification_definition_id: 'definition-1', specification_definition_name: 'Managed switch', specification_version: 1, lifecycle: 'active', specifications: { ports: 24, managed: true }, notes: 'Initial', checksum: 'b'.repeat(64), created_by: 'Catalog Owner', created_at: '2026-08-09T12:00:00Z',
    },
    revisions: [{
      id: 'revision-1', revision: 1, parent_id: null, specification_version_id: 'version-1', specification_definition_id: 'definition-1', specification_definition_name: 'Managed switch', specification_version: 1, lifecycle: 'active', specifications: { ports: 24, managed: true }, notes: 'Initial', checksum: 'b'.repeat(64), created_by: 'Catalog Owner', created_at: '2026-08-09T12:00:00Z',
    }],
  }],
}

function catalogClient(overrides: Partial<CatalogClient> = {}): CatalogClient {
  return {
    listProducts: vi.fn().mockResolvedValue({ results: [product], can_manage: true }),
    createProduct: vi.fn().mockResolvedValue(product),
    updateProduct: vi.fn().mockResolvedValue(product),
    archiveProduct: vi.fn().mockResolvedValue(undefined),
    listDefinitions: vi.fn().mockResolvedValue({ results: [definition], can_manage: true }),
    createDefinition: vi.fn().mockResolvedValue(definition),
    versionDefinition: vi.fn().mockResolvedValue(definition.versions[0]),
    createModel: vi.fn().mockResolvedValue(product.models[0]),
    reviseModel: vi.fn().mockResolvedValue(product.models[0]),
    archiveModel: vi.fn().mockResolvedValue(undefined),
    listPublicationChoices: vi.fn().mockResolvedValue({ results: [] }),
    associateDocument: vi.fn().mockResolvedValue({}),
    archiveDocumentAssociation: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

describe('Products', () => {
  it('shows supplier products, current specifications, and saved version history', async () => {
    const user = userEvent.setup()
    render(<Products workspace={workspace} client={catalogClient()} />)
    expect(await screen.findByRole('heading', { name: 'EdgeSwitch' })).toBeInTheDocument()
    expect(screen.getByText('ES-24 · Active · version 1')).toBeInTheDocument()
    expect(screen.getByText('24')).toBeInTheDocument()
    expect(screen.getByText('Yes')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show versions for EdgeSwitch 24' }))
    expect(screen.getByText(/Version 1 · Managed switch, template version 1/)).toBeInTheDocument()
    expect(screen.getByText(/Initial/)).toBeInTheDocument()
  })

  it('creates a product in the active supplier workspace', async () => {
    const createProduct = vi.fn().mockResolvedValue({ ...product, id: 'product-2', name: 'Cloud Gateway' })
    const api = catalogClient({ createProduct })
    const user = userEvent.setup()
    render(<Products workspace={workspace} client={api} />)
    await user.click(await screen.findByRole('button', { name: 'New product' }))
    const editor = screen.getByRole('heading', { name: 'New product' }).closest('section')!
    await user.type(within(editor).getByLabelText('Product name'), 'Cloud Gateway')
    await user.selectOptions(within(editor).getByLabelText('Type'), 'software')
    await user.type(within(editor).getByLabelText('Description'), 'Cloud-managed gateway')
    await user.click(within(editor).getByRole('button', { name: 'Create product' }))
    await waitFor(() => expect(createProduct).toHaveBeenCalledWith(workspace, {
      name: 'Cloud Gateway', kind: 'software', description: 'Cloud-managed gateway', unit_amount: null, currency: '',
    }))
  })

  it('builds a controlled specification template and saves a new version', async () => {
    const createDefinition = vi.fn<CatalogClient['createDefinition']>().mockResolvedValue(definition)
    const versionDefinition = vi.fn().mockResolvedValue(definition.versions[0])
    const api = catalogClient({ createDefinition, versionDefinition })
    const user = userEvent.setup()
    render(<Products workspace={workspace} client={api} />)
    await user.click(await screen.findByRole('tab', { name: 'Specification templates' }))
    await user.click(screen.getByRole('button', { name: 'New specification template' }))
    let editor = screen.getByRole('heading', { name: 'New specification template' }).closest('section')!
    await user.type(within(editor).getByLabelText('Template name'), 'Wireless access point')
    await user.type(within(editor).getByLabelText('Import name'), 'radio_count')
    await user.type(within(editor).getByLabelText('Display label'), 'Radio count')
    await user.selectOptions(within(editor).getByLabelText('Value type'), 'integer')
    await user.click(within(editor).getByLabelText('Required'))
    await user.click(within(editor).getByRole('button', { name: 'Create template' }))
    await waitFor(() => expect(createDefinition).toHaveBeenCalledOnce())
    const submittedDefinition = createDefinition.mock.calls[0][1]
    expect(submittedDefinition.name).toBe('Wireless access point')
    expect(submittedDefinition.schema.additionalProperties).toBe(false)
    expect(submittedDefinition.schema.required).toEqual(['radio_count'])
    await user.click(screen.getByRole('button', { name: 'Update template' }))
    editor = screen.getByRole('heading', { name: 'Update Managed switch' }).closest('section')!
    await user.click(within(editor).getByRole('button', { name: 'Save new version' }))
    await waitFor(() => expect(versionDefinition).toHaveBeenCalledWith(workspace, 'definition-1', expect.objectContaining({ additionalProperties: false })))
  })

  it('creates and revises a model from schema-driven fields', async () => {
    const createModel = vi.fn().mockResolvedValue(product.models[0])
    const reviseModel = vi.fn().mockResolvedValue(product.models[0])
    const api = catalogClient({ createModel, reviseModel })
    const user = userEvent.setup()
    render(<Products workspace={workspace} client={api} />)
    await user.click(await screen.findByRole('button', { name: 'Add model' }))
    let editor = screen.getByRole('heading', { name: 'Add model' }).closest('section')!
    await user.type(within(editor).getByLabelText('Model name'), 'EdgeSwitch 48')
    await user.type(within(editor).getByLabelText('Model number or SKU'), 'ES-48')
    await user.type(within(editor).getByLabelText('Port count *'), '48')
    await user.click(within(editor).getByLabelText('Managed'))
    await user.click(within(editor).getByRole('button', { name: 'Add model' }))
    await waitFor(() => expect(createModel).toHaveBeenCalledWith(workspace, 'product-1', expect.objectContaining({ specifications: { ports: 48, managed: true } })))
    await user.click(screen.getByRole('button', { name: 'Update model' }))
    editor = screen.getByRole('heading', { name: 'Update EdgeSwitch 24' }).closest('section')!
    await user.clear(within(editor).getByLabelText('Change notes'))
    await user.type(within(editor).getByLabelText('Change notes'), 'Reviewed specification')
    await user.click(within(editor).getByRole('button', { name: 'Save new version' }))
    await waitFor(() => expect(reviseModel).toHaveBeenCalledWith(workspace, 'product-1', 'model-1', expect.objectContaining({ base_revision_id: 'revision-1', notes: 'Reviewed specification' })))
  })

  it('adds a published document to an exact model', async () => {
    const associateDocument = vi.fn().mockResolvedValue({})
    const api = catalogClient({
      associateDocument,
      listPublicationChoices: vi.fn().mockResolvedValue({ results: [{
        id: 'publication-1', source_document_id: 'document-1',
        title: 'Installation guide', category: 'guide', content_digest: 'c'.repeat(64), published_at: '2026-08-10T12:00:00Z',
      }] }),
    })
    const user = userEvent.setup()
    render(<Products workspace={workspace} client={api} />)
    await user.click(await screen.findByRole('button', { name: 'Add document' }))
    await user.selectOptions(screen.getByLabelText('Published document'), 'publication-1')
    await user.selectOptions(screen.getByLabelText('Applies to'), 'model-1')
    const form = screen.getByLabelText('Published document').closest('.catalog-document-form') as HTMLElement
    await user.click(within(form).getByRole('button', { name: 'Add document' }))
    await waitFor(() => expect(associateDocument).toHaveBeenCalledWith(workspace, 'product-1', 'publication-1', 'model-1'))
  })

  it('renders empty, denial, loading failure, and mutation failure states', async () => {
    const denied = catalogClient({
      listProducts: vi.fn().mockResolvedValue({ results: [], can_manage: false }),
      listDefinitions: vi.fn().mockResolvedValue({ results: [], can_manage: false }),
    })
    const { unmount } = render(<Products workspace={workspace} client={denied} />)
    expect(await screen.findByText('No products match this view.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New product' })).not.toBeInTheDocument()
    unmount()
    render(<Products workspace={workspace} client={catalogClient({ listProducts: vi.fn().mockRejectedValue(new Error('Denied')) })} />)
    expect(await screen.findByRole('heading', { name: 'Products unavailable' })).toBeInTheDocument()
  })

  it('explains product and model archive consequences before making the change', async () => {
    const archiveProduct = vi.fn().mockResolvedValue(undefined)
    const archiveModel = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(<Products workspace={workspace} client={catalogClient({ archiveProduct, archiveModel })} />)

    await user.click(await screen.findByRole('button', { name: 'Archive EdgeSwitch' }))
    let confirmation = screen.getByRole('alertdialog')
    expect(confirmation).toHaveTextContent('Existing assets keep their saved product and model details.')
    await user.click(within(confirmation).getByRole('button', { name: 'Cancel' }))

    await user.click(screen.getByRole('button', { name: 'Archive model EdgeSwitch 24' }))
    confirmation = screen.getByRole('alertdialog')
    expect(confirmation).toHaveTextContent('Existing assets keep their saved model details.')
    await user.click(within(confirmation).getByRole('button', { name: 'Archive model' }))
    await waitFor(() => expect(archiveModel).toHaveBeenCalledWith(workspace, 'product-1', 'model-1'))
    expect(archiveProduct).not.toHaveBeenCalled()
  })
})
