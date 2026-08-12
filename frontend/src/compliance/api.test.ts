import { beforeEach, describe, expect, it, vi } from 'vitest'

import { browserComplianceClient } from './api'

describe('compliance API client', () => {
  beforeEach(() => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=compliance-csrf' })
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ results: [] }), { status: 200 }))))
  })

  it('keeps evidence reads and writes inside an encoded organization workspace', async () => {
    const workspace = { kind: 'organization', id: 'client/1' } as never
    await browserComplianceClient.evidence(workspace)
    await browserComplianceClient.createEvidence(workspace, {
      title: 'Access review', kind: 'url', summary: '', source_url: 'https://example.test/report',
      source_entity_id: null, collection_start: null, collection_end: null,
    })
    await browserComplianceClient.reviewEvidence(workspace, 'evidence/1', {
      status: 'accepted', decision: 'Reviewed', note: '',
    })
    await browserComplianceClient.linkEvidence(workspace, 'assignment/1', 'evidence/1')
    await browserComplianceClient.risks(workspace)
    const risk = {
      title: 'Recovery gap', description: '', assignment_id: null, likelihood: 3, impact: 4,
      status: 'open', treatment: 'mitigate', treatment_plan: '', owner_id: null, due_date: null,
      decision: 'Track', note: '',
    } as const
    await browserComplianceClient.createRisk(workspace, risk)
    await browserComplianceClient.reviewRisk(workspace, 'risk/1', risk)

    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2F1/compliance/evidence?page=1&page_size=100',
      expect.any(Object),
    )
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2F1/compliance/evidence/evidence%2F1/review',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2F1/compliance/assignments/assignment%2F1/evidence',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ evidence_id: 'evidence/1' }) }),
    )
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2F1/compliance/risks/risk%2F1/review',
      expect.objectContaining({ method: 'POST' }),
    )
    const write = vi.mocked(fetch).mock.calls.find(([url, options]) =>
      url === '/api/v1/workspaces/organizations/client%2F1/compliance/evidence' && options?.method === 'POST')
    expect((write?.[1]?.headers as Record<string, string>)['X-CSRFToken']).toBe('compliance-csrf')
  })

  it('uses the non-aggregating MSP route and preserves safe server errors', async () => {
    await browserComplianceClient.evidence(null)
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/workspaces/msp/compliance/evidence?page=1&page_size=100',
      expect.any(Object),
    )

    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ error: { message: 'Evidence is unavailable.' } }), { status: 404 }))
    await expect(browserComplianceClient.evidence(null)).rejects.toThrow('Evidence is unavailable.')
  })

  it('routes catalog reads and writes through the selected workspace', async () => {
    const workspace = { kind: 'organization', id: 'client-2' } as never
    await browserComplianceClient.list(workspace, 'policy & risk', 2)
    await browserComplianceClient.revisions(workspace, 'framework/1')
    await browserComplianceClient.assignments(workspace, 'framework/1')
    await browserComplianceClient.createVersion(workspace, 'framework/1', {
      version_label: '2026.2', description: '', source_url: '', controls: [],
    })
    await browserComplianceClient.reviewControl(workspace, 'framework/1', 'control/1', {
      applicability: 'applicable', implementation_status: 'implemented', owner_id: null,
      review_due_date: null, decision: 'Reviewed', note: '',
    })

    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client-2/compliance/frameworks?q=policy+%26+risk&page=2&page_size=50',
      expect.any(Object),
    )
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client-2/compliance/frameworks/framework%2F1/controls/control%2F1/review',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('falls back safely for legacy and non-JSON failures without a CSRF cookie', async () => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'session=present; theme=system' })
    await browserComplianceClient.list(null, '', 1)
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Catalog unavailable.' }), { status: 403 }))
    await expect(browserComplianceClient.create(null, {
      name: 'Baseline', version_label: '1', description: '', source_url: '', controls: [],
    })).rejects.toThrow('Catalog unavailable.')

    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response('not-json', { status: 500 }))
    await expect(browserComplianceClient.create(null, {
      name: 'Baseline', version_label: '1', description: '', source_url: '', controls: [],
    })).rejects.toThrow('The compliance catalog request failed.')

    const writes = vi.mocked(fetch).mock.calls.filter(([, options]) => options?.method === 'POST')
    expect(writes).toHaveLength(2)
    expect((writes[0][1]?.headers as Record<string, string>)['X-CSRFToken']).toBe('')
  })
})
