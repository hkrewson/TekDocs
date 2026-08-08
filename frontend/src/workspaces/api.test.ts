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
    })
  })

  it('returns one safe unavailable state without server response content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('foreign organization details', { status: 404 })))

    await expect(browserWorkspaceClient.loadOrganization(workspace.id)).rejects.toEqual(
      new AuthRequestError('That organization workspace is no longer available.', 404),
    )
  })
})
