import { beforeEach, describe, expect, it, vi } from 'vitest'

import { browserDomainsClient } from './api'

describe('domains API client', () => {
  beforeEach(() => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=domain-csrf' })
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify({}), { status: 200 }),
    )))
  })

  it('uses exact organization routes and CSRF-protected monitoring writes', async () => {
    const workspace = { kind: 'organization', id: 'client/1' } as never
    await browserDomainsClient.list(workspace)
    await browserDomainsClient.create(workspace, { name: 'example.com' } as never)
    await browserDomainsClient.monitoring(workspace, 'domain/1')
    await browserDomainsClient.scan(workspace, 'domain/1')
    await browserDomainsClient.listCertificates(workspace, 'domain/1')
    await browserDomainsClient.createCertificate(workspace, 'domain/1', 'https', null)
    await browserDomainsClient.certificateMonitoring(workspace, 'domain/1', 'endpoint/1')
    await browserDomainsClient.scanCertificate(workspace, 'domain/1', 'endpoint/1')

    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2F1/domains/domain%2F1/monitoring',
      expect.objectContaining({ credentials: 'same-origin' }),
    )
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2F1/domains/domain%2F1/monitoring',
      expect.objectContaining({ method: 'POST' }),
    )
    const scan = vi.mocked(fetch).mock.calls.find(([, options]) => options?.method === 'POST' && options.body === '{}')
    expect((scan?.[1]?.headers as Record<string, string>)['X-CSRFToken']).toBe('domain-csrf')
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2F1/domains/domain%2F1/certificates/endpoint%2F1/monitoring',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('uses the explicit MSP boundary and surfaces structured errors', async () => {
    await browserDomainsClient.list(null)
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/msp/domains', expect.any(Object))

    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ error: { message: 'Monitoring denied.' } }), { status: 403 }))
    await expect(browserDomainsClient.monitoring(null, 'domain-1')).rejects.toThrow('Monitoring denied.')
  })

  it('uses safe defaults when CSRF or structured error details are unavailable', async () => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: '' })
    await browserDomainsClient.scan(null, 'domain-1')
    const scan = vi.mocked(fetch).mock.calls.find(([, options]) => options?.method === 'POST')
    expect((scan?.[1]?.headers as Record<string, string>)['X-CSRFToken']).toBe('')

    vi.mocked(fetch).mockResolvedValueOnce(new Response('not-json', { status: 500 }))
    await expect(browserDomainsClient.list(null)).rejects.toThrow('The domain request failed.')
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Collection unavailable.' }), { status: 503 }))
    await expect(browserDomainsClient.list(null)).rejects.toThrow('Collection unavailable.')
  })
})
