import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { AuthenticatedContext } from '../auth/api'
import { ClientPortal } from './ClientPortal'

const context: AuthenticatedContext = {
  surface: 'client_portal',
  tenant: { id: 'tenant-1', name: 'MSP' },
  organization: { id: 'org-1', name: 'Example Client' },
  user: { id: 'user-1', email: 'reader@example.com', display_name: 'Client Reader' },
  role: 'client_user', permissions: [],
}

afterEach(() => vi.restoreAllMocks())

describe('ClientPortal', () => {
  it('lists and opens only explicitly client-visible STATIC documentation accessibly', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/api/v1/portal/documents')) return Promise.resolve(new Response(JSON.stringify({ count: 1, has_more: false, next_cursor: null, results: [{ id: 'pub-1', title: 'Access guide', category: 'guide', reason: 'Approved', lifecycle_state: 'published', retention: 'permanent', retention_review_on: null, published_at: '2026-08-11T12:00:00Z', content_digest: 'abc', source_kind: 'organization_document', visibility: 'client_visible', artifacts: [] }] }), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ id: 'pub-1', title: 'Access guide', category: 'guide', reason: 'Approved', lifecycle_state: 'published', retention: 'permanent', retention_review_on: null, published_at: '2026-08-11T12:00:00Z', content_digest: 'abc', source_kind: 'organization_document', visibility: 'client_visible', artifacts: [], sanitized_html: '<h1>Safe guide</h1><script>alert(1)</script>' }), { status: 200 }))
    })
    const { container } = render(<ClientPortal context={context} onSignOut={vi.fn()} signingOut={false} signOutError={null} />)
    expect(await screen.findByRole('button', { name: /access guide/i })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /access guide/i }))
    expect(await screen.findByRole('heading', { name: 'Safe guide' })).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    expect(screen.getByRole('button', { name: /all documents/i })).toBeInTheDocument()
  })

  it('shows a clear empty state without exposing MSP navigation', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ count: 0, has_more: false, next_cursor: null, results: [] }), { status: 200 }))
    render(<ClientPortal context={context} onSignOut={vi.fn()} signingOut={false} signOutError={null} />)
    expect(await screen.findByText(/no documentation has been published/i)).toBeInTheDocument()
    expect(screen.queryByText('Organizations')).not.toBeInTheDocument()
  })

  it('appends a bounded older page without replacing the current document list', async () => {
    const document = (id: string, title: string) => ({ id, title, category: 'guide', reason: 'Approved', lifecycle_state: 'published', retention: 'permanent', retention_review_on: null, published_at: '2026-08-11T12:00:00Z', content_digest: id, source_kind: 'organization_document', visibility: 'client_visible', artifacts: [] })
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ count: 1, has_more: true, next_cursor: 'signed-cursor', results: [document('pub-1', 'Current guide')] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ count: 1, has_more: false, next_cursor: null, results: [document('pub-2', 'Older guide')] }), { status: 200 }))
    const user = userEvent.setup()
    render(<ClientPortal context={context} onSignOut={vi.fn()} signingOut={false} signOutError={null} />)

    await user.click(await screen.findByRole('button', { name: 'Load more documents' }))
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/portal/documents?cursor=signed-cursor')
    expect(screen.getByRole('button', { name: /current guide/i })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /older guide/i })).toBeInTheDocument()
  })
})
