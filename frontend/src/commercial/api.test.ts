import { beforeEach, describe, expect, it, vi } from 'vitest'
import { browserCommercialClient } from './api'

describe('commercial API client', () => {
  beforeEach(() => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=commercial-csrf' })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ results: [] }), { status: 200 }))),
    )
  })

  it('uses exact client routes, encoded identifiers, CSRF, and every mutation contract', async () => {
    const workspace = { kind: 'organization', id: 'client/1' } as never
    await browserCommercialClient.listContracts(workspace, 'managed support', 2)
    await browserCommercialClient.providerChoices(workspace)
    await browserCommercialClient.createContract(workspace, { name: 'Managed support' })
    await browserCommercialClient.updateContract(workspace, 'contract/1', { status: 'active' })
    await browserCommercialClient.createCost(workspace, 'contract/1', { amount: '25.00' })
    await browserCommercialClient.updateCost(workspace, 'contract/1', 'cost/1', { amount: '30.00' })
    await browserCommercialClient.archiveCost(workspace, 'contract/1', 'cost/1')
    await browserCommercialClient.archiveContract(workspace, 'contract/1')

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2F1/contracts?q=managed+support&page=2&page_size=50',
      expect.objectContaining({ credentials: 'same-origin' }),
    )
    const costPatch = vi.mocked(fetch).mock.calls.find(([path, options]) => {
      const value = typeof path === 'string' ? path : path instanceof URL ? path.href : path.url
      return value.endsWith('/contracts/contract%2F1/costs/cost%2F1') && options?.method === 'PATCH'
    })
    expect(costPatch?.[0]).toBe('/api/v1/workspaces/organizations/client%2F1/contracts/contract%2F1/costs/cost%2F1')
    expect((costPatch?.[1]?.headers as Record<string, string>)['X-CSRFToken']).toBe('commercial-csrf')
  })

  it('uses the explicit MSP contracts boundary', async () => {
    await browserCommercialClient.listContracts({ kind: 'msp', id: 'tenant/1' } as never, '', 1)
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      '/api/v1/workspaces/msp/contracts?q=&page=1&page_size=50',
      expect.objectContaining({ credentials: 'same-origin' }),
    )
  })

  it('surfaces nested validation responses', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ amount: ['A non-negative amount is required.'] }), { status: 400 }),
    )
    await expect(browserCommercialClient.listContracts({ kind: 'organization', id: 'client' } as never, '', 1)).rejects.toThrow(
      'A non-negative amount is required.',
    )
  })
})
