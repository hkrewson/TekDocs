import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthRequestError } from '../auth/api'
import { browserWorkspaceClient } from './api'
import type { WorkspaceContext } from './api'

const workspace: WorkspaceContext = {
  kind: 'organization',
  id: '00000000-0000-4000-8000-000000000010',
  name: 'Acme Dental',
  classifications: ['client', 'vendor'],
  capabilities: ['overview', 'documentation', 'people', 'assets', 'networks', 'credentials', 'products'],
  organization: {
    id: '00000000-0000-4000-8000-000000000010',
    name: 'Acme Dental',
    legal_name: 'Acme Dental Associates, LLC',
    website: 'https://acme.example.com',
    classifications: ['client', 'vendor'],
    created_at: '2026-08-08T12:00:00Z',
    updated_at: '2026-08-08T12:00:00Z',
  },
}

describe('browserWorkspaceClient', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('resolves an organization through its stable entity identifier', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(workspace), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(browserWorkspaceClient.loadOrganization(workspace.id)).resolves.toEqual(workspace)
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/workspaces/organizations/${workspace.id}`, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal: undefined,
    })
  })

  it('encodes bounded workspace search parameters', async () => {
    const result = { results: [], page: 2, page_size: 15, has_more: false }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(result), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(browserWorkspaceClient.searchOrganizations('Acme & Sons', 2, undefined, 'client')).resolves.toEqual(result)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/workspaces/organizations?q=Acme+%26+Sons&page=2&page_size=15&classification=client', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal: undefined,
    })
  })

  it('returns one safe unavailable state without server response content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('foreign organization details', { status: 404 })))

    await expect(browserWorkspaceClient.loadOrganization(workspace.id)).rejects.toEqual(
      new AuthRequestError('That organization workspace is no longer available.', 404),
    )
  })
})
