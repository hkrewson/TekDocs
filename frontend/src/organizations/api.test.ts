import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthRequestError } from '../auth/api'
import { browserOrganizationClient } from './api'
import type { Organization, OrganizationInput, OrganizationQuery } from './api'

const input: OrganizationInput = {
  name: 'Acme Dental',
  legal_name: 'Acme Dental Associates, LLC',
  website: 'https://acme.example.com',
  classifications: ['client', 'partner'],
}

const organization: Organization = {
  id: '00000000-0000-4000-8000-000000000010',
  ...input,
  access_mode: 'assigned_only',
  created_at: '2026-08-08T12:00:00Z',
  updated_at: '2026-08-08T12:00:00Z',
}
const query: OrganizationQuery = { q: 'acme dental', classification: 'client', ordering: '-name', page: 2, page_size: 25 }

describe('browserOrganizationClient', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=organization-csrf; path=/'
  })

  it('loads the tenant organization collection', async () => {
    const payload = { results: [organization], page: 2, page_size: 25, count: 26, has_more: false }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(browserOrganizationClient.list(query)).resolves.toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/organizations?ordering=-name&page=2&page_size=25&q=acme+dental&classification=client', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal: undefined,
    })
  })

  it('retrieves one organization for direct record links', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(organization), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(browserOrganizationClient.retrieve(organization.id)).resolves.toEqual(organization)
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/organizations/${organization.id}`, {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal: undefined,
    })
  })

  it('sends CSRF-protected create, update, and archive requests', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(organization), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...organization, name: 'Acme Health' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await browserOrganizationClient.create(input)
    await browserOrganizationClient.update(organization.id, { ...input, name: 'Acme Health' })
    await browserOrganizationClient.archive(organization.id)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/organizations', expect.objectContaining({
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': 'organization-csrf',
      },
      body: JSON.stringify(input),
    }))
    expect(fetchMock).toHaveBeenNthCalledWith(2, `/api/v1/organizations/${organization.id}`, expect.objectContaining({
      method: 'PATCH',
      body: JSON.stringify({ ...input, name: 'Acme Health' }),
    }))
    expect(fetchMock).toHaveBeenNthCalledWith(3, `/api/v1/organizations/${organization.id}`, expect.objectContaining({
      method: 'DELETE',
    }))
  })

  it('reports authorization denial without exposing server response content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('sensitive detail', { status: 403 })))

    await expect(browserOrganizationClient.create(input)).rejects.toEqual(
      new AuthRequestError('Your account is not authorized for organization administration.', 403),
    )
  })
})
