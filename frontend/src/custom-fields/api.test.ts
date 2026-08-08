import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthRequestError } from '../auth/api'
import { browserCustomFieldsClient } from './api'
import type { CustomFieldDefinitionInput } from './api'

const organizationId = '00000000-0000-4000-8000-000000000010'
const definitionId = '00000000-0000-4000-8000-000000000020'
const entityId = '00000000-0000-4000-8000-000000000030'
const input: CustomFieldDefinitionInput = {
  key: 'door_code', entity_type: 'site', label: 'Door code', description: '', required: false, field_type: 'text', display_order: 2, options: [],
}

describe('browserCustomFieldsClient', () => {
  beforeEach(() => { document.cookie = 'csrftoken=custom-fields-csrf; path=/' })

  it('loads MSP and organization definitions from their distinct scopes', async () => {
    const payload = { results: [], count: 0 }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(payload), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(payload), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await browserCustomFieldsClient.listDefinitions({})
    await browserCustomFieldsClient.listDefinitions({ organizationId })

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/custom-field-definitions', expect.objectContaining({ credentials: 'same-origin' }))
    expect(fetchMock).toHaveBeenNthCalledWith(2, `/api/v1/workspaces/organizations/${organizationId}/custom-field-definitions`, expect.any(Object))
  })

  it('uses CSRF-protected definition lifecycle mutations', async () => {
    const definition = { id: definitionId }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(definition), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ definition, migration_impact: { total: 0, compatible: 0, incompatible: 0 } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await browserCustomFieldsClient.createDefinition({ organizationId }, input)
    await browserCustomFieldsClient.createVersion({ organizationId }, definitionId, input)
    await browserCustomFieldsClient.archiveDefinition({ organizationId }, definitionId)

    const base = `/api/v1/workspaces/organizations/${organizationId}/custom-field-definitions`
    expect(fetchMock).toHaveBeenNthCalledWith(1, base, expect.objectContaining({ method: 'POST' }))
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(request.headers).toEqual(expect.objectContaining({ 'X-CSRFToken': 'custom-fields-csrf' }))
    expect(fetchMock).toHaveBeenNthCalledWith(2, `${base}/${definitionId}`, expect.objectContaining({ method: 'PATCH' }))
    expect(fetchMock).toHaveBeenNthCalledWith(3, `${base}/${definitionId}`, expect.objectContaining({ method: 'DELETE' }))
  })

  it('loads, sets, and clears values through the entity scope', async () => {
    const payload = { entity_id: entityId, entity_type: 'site', fields: [] }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(payload), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(payload), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await browserCustomFieldsClient.listEntityFields({}, entityId)
    await browserCustomFieldsClient.setEntityValue({}, entityId, definitionId, '4231')
    await browserCustomFieldsClient.clearEntityValue({}, entityId, definitionId)

    const base = `/api/v1/entities/${entityId}/custom-fields`
    expect(fetchMock).toHaveBeenNthCalledWith(1, base, expect.any(Object))
    expect(fetchMock).toHaveBeenNthCalledWith(2, `${base}/${definitionId}`, expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ value: '4231' }) }))
    expect(fetchMock).toHaveBeenNthCalledWith(3, `${base}/${definitionId}`, expect.objectContaining({ method: 'DELETE' }))
  })

  it('returns a value-free denial message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('private detail', { status: 403 })))
    await expect(browserCustomFieldsClient.listDefinitions({})).rejects.toEqual(
      new AuthRequestError('Your account is not authorized to manage custom fields in this workspace.', 403),
    )
  })
})
