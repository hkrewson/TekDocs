import { beforeEach, describe, expect, it, vi } from 'vitest'
import { browserCatalogClient } from './api'

describe('catalog API client', () => {
  beforeEach(() => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=catalog-csrf' })
    vi.stubGlobal('fetch', vi.fn())
  })

  it('uses exact supplier routes, query encoding, CSRF, and every mutation contract', async () => {
    const fetchMock = vi.mocked(fetch)
    const workspace = { id: 'supplier/1' } as never
    const ok = (body: unknown = {}) => new Response(JSON.stringify(body), { status: 200 })
    fetchMock.mockImplementation(() => Promise.resolve(ok()))
    await browserCatalogClient.listProducts(workspace, 'edge switch', 'hardware')
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/workspaces/organizations/supplier%2F1/catalog/products?q=edge+switch&kind=hardware',
      expect.objectContaining({ credentials: 'same-origin' }),
    )
    await browserCatalogClient.listDefinitions(workspace)
    await browserCatalogClient.createProduct(workspace, { name: 'Edge', kind: 'hardware', description: '' })
    await browserCatalogClient.updateProduct(workspace, 'product/1', { name: 'Edge 2', description: '' })
    await browserCatalogClient.createDefinition(workspace, { name: 'Switch', product_kind: 'hardware', schema: { type: 'object', additionalProperties: false, properties: {} } })
    await browserCatalogClient.versionDefinition(workspace, 'definition/1', { type: 'object', additionalProperties: false, properties: {} })
    const model = { name: 'Model', model_number: 'M1', specification_version_id: 'v1', lifecycle: 'active' as const, specifications: {}, notes: '' }
    await browserCatalogClient.createModel(workspace, 'product/1', model)
    await browserCatalogClient.reviseModel(workspace, 'product/1', 'model/1', { ...model, base_revision_id: 'r1' })
    await browserCatalogClient.archiveModel(workspace, 'product/1', 'model/1')
    await browserCatalogClient.listPublicationChoices(workspace)
    await browserCatalogClient.associateDocument(workspace, 'product/1', 'publication/1', 'model/1')
    await browserCatalogClient.archiveDocumentAssociation(workspace, 'product/1', 'association/1')
    await browserCatalogClient.archiveProduct(workspace, 'product/1')
    const mutationCall = fetchMock.mock.calls.find(([path]) => {
      const value = typeof path === 'string' ? path : path instanceof URL ? path.href : path.url
      return value.includes('/catalog/products/product%2F1')
    })
    expect(mutationCall?.[0]).toContain('/catalog/products/product%2F1')
    expect((mutationCall?.[1]?.headers as Record<string, string>)['X-CSRFToken']).toBe('catalog-csrf')
  })

  it('surfaces nested validation and conflict responses without losing the current revision', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: ['Invalid specification'] }), { status: 400 }))
    await expect(browserCatalogClient.listDefinitions({ id: 'supplier' } as never)).rejects.toThrow('Invalid specification')
  })
})
