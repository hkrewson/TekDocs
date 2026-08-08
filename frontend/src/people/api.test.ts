import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthRequestError } from '../auth/api'
import { browserPeopleClient } from './api'
import type { PeopleQuery, PersonInput, PersonRecord } from './api'

const input: PersonInput = {
  full_name: 'Jordan Avery',
  preferred_name: 'Jordy',
  kind: 'employee',
  role: 'Systems Administrator',
  responsibility: 'Network operations',
  location: 'North Office',
  office: 'Desk 214',
  phone: '+1 555 010 0240',
  email: 'jordan@example.com',
}
const person: PersonRecord = {
  id: '00000000-0000-4000-8000-000000000020',
  association_id: '00000000-0000-4000-8000-000000000021',
  organization_id: '00000000-0000-4000-8000-000000000010',
  ...input,
  created_at: '2026-08-08T12:00:00Z',
  updated_at: '2026-08-08T12:00:00Z',
}
const query: PeopleQuery = { q: 'north', filter_field: 'role', filter_value: 'admin', ordering: '-full_name', page: 2, page_size: 25 }

describe('browserPeopleClient', () => {
  beforeEach(() => { document.cookie = 'csrftoken=people-csrf; path=/' })

  it('loads a bounded organization query with encoded filters', async () => {
    const payload = { results: [person], page: 2, page_size: 25, count: 26, has_more: false }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(browserPeopleClient.list({ organizationId: person.organization_id! }, query)).resolves.toEqual(payload)
    const requestPath = fetchMock.mock.calls[0][0] as string
    expect(requestPath).toContain(`/api/v1/workspaces/organizations/${person.organization_id}/people?`)
    expect(requestPath).toContain('q=north')
    expect(requestPath).toContain('filter_field=role')
    expect(requestPath).toContain('filter_value=admin')
    expect(requestPath).toContain('ordering=-full_name')
  })

  it('sends scoped CSRF-protected mutations', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(person), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...person, preferred_name: 'Jordan' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const scope = { organizationId: person.organization_id! }

    await browserPeopleClient.create(scope, input)
    await browserPeopleClient.update(scope, person.id, { ...input, preferred_name: 'Jordan' })
    await browserPeopleClient.archive(scope, person.id)

    const base = `/api/v1/workspaces/organizations/${person.organization_id}/people`
    expect(fetchMock).toHaveBeenNthCalledWith(1, base, {
      method: 'POST',
      credentials: 'same-origin',
      body: JSON.stringify(input),
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': 'people-csrf',
      },
    })
    expect(fetchMock).toHaveBeenNthCalledWith(2, `${base}/${person.id}`, expect.objectContaining({ method: 'PATCH' }))
    expect(fetchMock).toHaveBeenNthCalledWith(3, `${base}/${person.id}`, expect.objectContaining({ method: 'DELETE' }))
  })

  it('reports denial without displaying response content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('private policy detail', { status: 403 })))

    await expect(browserPeopleClient.create({}, input)).rejects.toEqual(
      new AuthRequestError('Your account is not authorized to manage people in this workspace.', 403),
    )
  })
})
