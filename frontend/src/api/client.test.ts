import { createTekDocsApiClient, idempotencyHeaders } from './client'

describe('generated API client boundary', () => {
  it('uses generated paths with same-origin JSON and CSRF conventions', async () => {
    document.cookie = 'csrftoken=generated-client-csrf'
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      name: 'TekDocs API', version: '0.6.1', status: 'pre-alpha', api_version: 'v1',
      schema_url: '/api/v1/schema/', documentation_url: '/api/v1/docs/', conventions: {},
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    const client = createTekDocsApiClient()
    const { data, error } = await client.GET('/api/v1/')

    expect(error).toBeUndefined()
    expect(data?.api_version).toBe('v1')
    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.credentials).toBe('same-origin')
    expect(request.headers.get('Accept')).toBe('application/json')
  })

  it('constructs only bounded idempotency headers', () => {
    expect(idempotencyHeaders('asset-import:retry-0001')).toEqual({ 'Idempotency-Key': 'asset-import:retry-0001' })
    expect(() => idempotencyHeaders('short')).toThrow(/8–200/)
    expect(() => idempotencyHeaders('contains a space')).toThrow(/allowed ASCII/)
  })
})
