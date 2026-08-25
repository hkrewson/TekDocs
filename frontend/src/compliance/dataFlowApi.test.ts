import { beforeEach, expect, it, vi } from 'vitest'
import { browserDataFlowClient } from './dataFlowApi'

beforeEach(() => {
  Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=flow-csrf' })
  vi.stubGlobal('fetch', vi.fn())
})

it('reads an organization workspace through its scoped route with encoded identifiers', async () => {
  const fetchMock = vi.mocked(fetch)
  fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ results: [], count: 0 }), { status: 200 })))
  const workspace = { id: 'org/1' } as never

  await browserDataFlowClient.list(workspace, 2)
  await browserDataFlowClient.revisions(workspace, 'flow/1')

  expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/workspaces/organizations/org%2F1/compliance/data-flows?page=2&page_size=50')
  expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/workspaces/organizations/org%2F1/compliance/data-flows/flow%2F1/revisions')
})

it('reads the MSP workspace through its own route rather than an organization one', async () => {
  const fetchMock = vi.mocked(fetch)
  fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({}), { status: 200 })))

  await browserDataFlowClient.choices(null)

  expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/workspaces/msp/compliance/data-flows/choices')
})

it('carries the CSRF token on a write', async () => {
  const fetchMock = vi.mocked(fetch)
  fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({}), { status: 200 })))

  await browserDataFlowClient.archive(null, 'flow-1')

  const request = fetchMock.mock.calls.at(-1)?.[1]
  expect(request?.method).toBe('DELETE')
  expect((request?.headers as Record<string, string>)['X-CSRFToken']).toBe('flow-csrf')
})

it('repeats the field message the server refused with', async () => {
  vi.mocked(fetch).mockImplementation(() => Promise.resolve(new Response(JSON.stringify({
    error: { fields: { detail: ['An external source requires a name.'] } },
  }), { status: 400, headers: { 'Content-Type': 'application/json' } })))

  await expect(browserDataFlowClient.create(null, {} as never)).rejects.toThrow('An external source requires a name.')
})

it('stays generic when a refusal explains nothing', async () => {
  vi.mocked(fetch).mockImplementation(() => Promise.resolve(new Response('<html>nope</html>', { status: 500 })))

  await expect(browserDataFlowClient.create(null, {} as never)).rejects.toThrow('The data-flow request was not completed.')
})
