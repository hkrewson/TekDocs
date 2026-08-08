import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthRequestError } from '../auth/api'
import { browserSitesClient } from './api'
import type { LocationInput, SiteInput, SiteRecord } from './api'

const scope = { organizationId: '00000000-0000-4000-8000-000000000010' }
const siteInput: SiteInput = {
  name: 'North Campus', code: 'NORTH', address_line_1: '100 Main Street', address_line_2: '', city: 'Madison', region: 'WI', postal_code: '53703', country_code: 'US', timezone: 'America/Chicago', phone: '',
}
const site: SiteRecord = {
  id: '00000000-0000-4000-8000-000000000020', organization_id: scope.organizationId, ...siteInput, locations: [], created_at: '2026-08-08T12:00:00Z', updated_at: '2026-08-08T12:00:00Z',
}
const locationInput: LocationInput = { name: 'Office 214', kind: 'office', code: '214', parent_id: null }

describe('browserSitesClient', () => {
  beforeEach(() => { document.cookie = 'csrftoken=sites-csrf; path=/' })

  it('loads an encoded workspace search', async () => {
    const payload = { results: [site], count: 1 }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(browserSitesClient.list(scope, 'North & Main')).resolves.toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v1/workspaces/organizations/${scope.organizationId}/sites?q=North+%26+Main`,
      expect.objectContaining({ credentials: 'same-origin' }),
    )
  })

  it('sends scoped CSRF-protected site and location mutations', async () => {
    const location = { id: '00000000-0000-4000-8000-000000000030', site_id: site.id, ...locationInput, created_at: site.created_at, updated_at: site.updated_at }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(site), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(location), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...location, name: 'Office 215' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await browserSitesClient.create(scope, siteInput)
    await browserSitesClient.createLocation(scope, site.id, locationInput)
    await browserSitesClient.updateLocation(scope, site.id, location.id, { name: 'Office 215' })
    await browserSitesClient.archiveLocation(scope, site.id, location.id)

    const base = `/api/v1/workspaces/organizations/${scope.organizationId}/sites`
    expect(fetchMock).toHaveBeenNthCalledWith(1, base, expect.objectContaining({ method: 'POST', body: JSON.stringify(siteInput) }))
    expect(fetchMock).toHaveBeenNthCalledWith(2, `${base}/${site.id}/locations`, expect.objectContaining({ method: 'POST' }))
    expect(fetchMock).toHaveBeenNthCalledWith(3, `${base}/${site.id}/locations/${location.id}`, expect.objectContaining({ method: 'PATCH' }))
    expect(fetchMock).toHaveBeenNthCalledWith(4, `${base}/${site.id}/locations/${location.id}`, expect.objectContaining({ method: 'DELETE' }))
  })

  it('reports a value-free workspace denial', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('private detail', { status: 403 })))
    await expect(browserSitesClient.create({}, siteInput)).rejects.toEqual(
      new AuthRequestError('Your account is not authorized to manage sites in this workspace.', 403),
    )
  })
})
