import { beforeEach, describe, expect, it, vi } from 'vitest'

import { browserTaxonomiesClient } from './api'
import type { TaxonomyInput } from './api'

const taxonomyId = '10000000-0000-4000-8000-000000000001'
const organizationId = '20000000-0000-4000-8000-000000000001'
const input: TaxonomyInput = {
  key: 'technology',
  binding: 'document_tags',
  label: 'Technology',
  description: 'Approved technology names.',
  allow_local_terms: false,
  terms: [{ stable_key: 'entra-id', label: 'Entra ID', description: '', parent_key: '', aliases: ['Azure AD'], status: 'active', replacement_key: '', sort_order: 0 }],
}

describe('browserTaxonomiesClient', () => {
  beforeEach(() => { document.cookie = 'csrftoken=taxonomy-csrf; path=/' })

  it('uses the MSP and client catalog boundaries and all controlled lifecycle mutations', async () => {
    const fetchMock = vi.fn().mockImplementation(
      () => Promise.resolve(new Response(JSON.stringify({ results: [], count: 0 }), { status: 200 })),
    )
    vi.stubGlobal('fetch', fetchMock)

    await browserTaxonomiesClient.list()
    await browserTaxonomiesClient.list(organizationId)
    await browserTaxonomiesClient.create(input)
    await browserTaxonomiesClient.revise(taxonomyId, input)
    await browserTaxonomiesClient.archive(taxonomyId)
    await browserTaxonomiesClient.migration(false)
    await browserTaxonomiesClient.createLocalTerm?.(organizationId, taxonomyId, { stable_key: 'client-app', label: 'Client app', description: '', aliases: [] })

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/taxonomies', expect.objectContaining({ credentials: 'same-origin' }))
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/workspaces/organizations/${organizationId}/taxonomies`, expect.any(Object))
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/taxonomies/${taxonomyId}`, expect.objectContaining({ method: 'PATCH' }))
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/taxonomies/${taxonomyId}`, expect.objectContaining({ method: 'DELETE' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/taxonomies/migration', expect.objectContaining({ body: JSON.stringify({ apply: false }) }))
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/workspaces/organizations/${organizationId}/taxonomies/${taxonomyId}/terms`, expect.objectContaining({ method: 'POST' }))
    const calls = fetchMock.mock.calls as [string, RequestInit][]
    const mutation = calls.find(([, options]) => options.method === 'PATCH')
    expect((mutation?.[1].headers as Record<string, string>)['X-CSRFToken']).toBe('taxonomy-csrf')
  })

  it('reports safe catalog and mutation failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('private', { status: 403 })))
    await expect(browserTaxonomiesClient.list()).rejects.toThrow('Taxonomies could not be loaded.')

    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'A term hierarchy contains a cycle.' }), { status: 400 }))
    await expect(browserTaxonomiesClient.create(input)).rejects.toThrow('A term hierarchy contains a cycle.')
  })
})
