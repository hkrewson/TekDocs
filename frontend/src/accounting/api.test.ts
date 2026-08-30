import { beforeEach, describe, expect, it, vi } from 'vitest'

import { browserInvoiceClient } from './api'

describe('invoice API client', () => {
  beforeEach(() => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=invoice-csrf' })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({}), { status: 200 }))),
    )
  })

  it('uses encoded workspace and invoice routes for every draft and issue operation', async () => {
    const workspace = { kind: 'organization', id: 'client/1' } as never
    await browserInvoiceClient.list(workspace)
    await browserInvoiceClient.choices(workspace)
    await browserInvoiceClient.create(workspace, { currency: 'USD' })
    await browserInvoiceClient.update(workspace, 'invoice/1', { notes: 'Updated' })
    await browserInvoiceClient.remove(workspace, 'invoice/1')
    await browserInvoiceClient.addLine(workspace, 'invoice/1', { description: 'Service' })
    await browserInvoiceClient.updateLine(workspace, 'invoice/1', 'line/1', { quantity: '2' })
    await browserInvoiceClient.removeLine(workspace, 'invoice/1', 'line/1')
    await browserInvoiceClient.issueSettings()
    await browserInvoiceClient.saveIssueSettings({ invoice_prefix: 'INV' })
    await browserInvoiceClient.issue(workspace, 'invoice/1')
    await browserInvoiceClient.deliver(workspace, 'invoice/1', 'accounts@example.invalid')

    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/workspaces/msp/invoice-settings',
      expect.objectContaining({ credentials: 'same-origin' }),
    )
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/workspaces/msp/invoice-settings',
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ invoice_prefix: 'INV' }) }),
    )
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2F1/invoices/invoice%2F1/issue',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2F1/invoices/invoice%2F1/deliver',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ recipient: 'accounts@example.invalid' }) }),
    )
    expect(browserInvoiceClient.pdfUrl(workspace, 'invoice/1')).toContain('/invoice%2F1/pdf')
    expect(browserInvoiceClient.csvUrl(workspace, 'invoice/1')).toContain('/invoice%2F1/csv')
    const issue = vi.mocked(fetch).mock.calls.find(
      ([path, options]) => typeof path === 'string' && path.endsWith('/issue') && options?.method === 'POST',
    )
    expect((issue?.[1]?.headers as Record<string, string>)['X-CSRFToken']).toBe('invoice-csrf')
  })

  it('returns undefined for retained delete responses and surfaces nested validation errors', async () => {
    const workspace = { kind: 'organization', id: 'client' } as never
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify({}), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    await expect(browserInvoiceClient.remove(workspace, 'invoice')).resolves.toBeUndefined()

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ lines: [{ description: ['Resolve invoice keys first.'] }] }), { status: 400 }),
    )
    await expect(browserInvoiceClient.list(workspace)).rejects.toThrow('Resolve invoice keys first.')
  })

  it('uses a safe fallback when an error response is not JSON', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response('not-json', { status: 500 }))
    await expect(
      browserInvoiceClient.issueSettings(),
    ).rejects.toThrow('The invoice request failed.')
  })
})
