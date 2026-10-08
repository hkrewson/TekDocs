import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { AuthenticatedContext } from '../auth/api'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { ClientPortal } from './ClientPortal'

const context: AuthenticatedContext = {
  surface: 'client_portal',
  tenant: { id: 'tenant-1', name: 'MSP' },
  organization: { id: 'org-1', name: 'Example Client' },
  user: { id: 'user-1', email: 'reader@example.com', display_name: 'Client Reader' },
  role: 'client_user', permissions: [],
  mfa_enrollment_required: false,
}

afterEach(() => vi.restoreAllMocks())

function renderPortal(path = '/portal') {
  return render(<ApplicationRouter initialPath={path}><ClientPortal context={context} onSignOut={vi.fn()} signingOut={false} signOutError={null} /></ApplicationRouter>)
}

describe('ClientPortal', () => {
  it('provides direct keyboard access to the portal content', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ count: 0, has_more: false, next_cursor: null, results: [] }), { status: 200 }))
    renderPortal()

    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveAttribute('href', '#portal-main-content')
    expect(screen.getByRole('main')).toHaveAttribute('id', 'portal-main-content')
    expect(screen.getByRole('link', { name: 'New publications' })).toHaveAttribute('href', '/portal?section=publications')
  })

  it('lists and opens a document without exposing publication internals', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/api/v1/portal/invoices')) return Promise.resolve(new Response(JSON.stringify({ count: 0, results: [] }), { status: 200 }))
      if (url.endsWith('/api/v1/portal/documents')) return Promise.resolve(new Response(JSON.stringify({ count: 1, has_more: false, next_cursor: null, results: [{ id: 'pub-1', title: 'Access guide', category: 'guide', reason: 'Approved', lifecycle_state: 'published', retention: 'permanent', retention_review_on: null, published_at: '2026-08-11T12:00:00Z', content_digest: 'abc', source_kind: 'organization_document', visibility: 'client_visible', artifacts: [] }] }), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ id: 'pub-1', title: 'Access guide', category: 'guide', reason: 'Approved', lifecycle_state: 'published', retention: 'permanent', retention_review_on: null, published_at: '2026-08-11T12:00:00Z', content_digest: 'abc', source_kind: 'organization_document', visibility: 'client_visible', artifacts: [], sanitized_html: '<h1>Safe guide</h1><script>alert(1)</script>' }), { status: 200 }))
    })
    const { container } = renderPortal()
    expect(await screen.findByRole('button', { name: /access guide/i })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /access guide/i }))
    expect(await screen.findByRole('heading', { name: 'Safe guide' })).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    expect(screen.getByRole('button', { name: /all documents/i })).toBeInTheDocument()
    expect(screen.queryByText(/STATIC|Client visible/)).not.toBeInTheDocument()
  })

  it('shows a clear empty state without exposing MSP navigation', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ count: 0, has_more: false, next_cursor: null, results: [] }), { status: 200 }))
    renderPortal()
    expect(await screen.findByText(/no documents have been shared/i)).toBeInTheDocument()
    expect(screen.queryByText('Organizations')).not.toBeInTheDocument()
  })

  it('appends a bounded older page without replacing the current document list', async () => {
    const document = (id: string, title: string) => ({ id, title, category: 'guide', reason: 'Approved', lifecycle_state: 'published', retention: 'permanent', retention_review_on: null, published_at: '2026-08-11T12:00:00Z', content_digest: id, source_kind: 'organization_document', visibility: 'client_visible', artifacts: [] })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/api/v1/portal/invoices')) return Promise.resolve(new Response(JSON.stringify({ count: 0, results: [] }), { status: 200 }))
      if (url.includes('cursor=')) return Promise.resolve(new Response(JSON.stringify({ count: 1, has_more: false, next_cursor: null, results: [document('pub-2', 'Older guide')] }), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ count: 1, has_more: true, next_cursor: 'signed-cursor', results: [document('pub-1', 'Current guide')] }), { status: 200 }))
    })
    const user = userEvent.setup()
    renderPortal()

    await user.click(await screen.findByRole('button', { name: 'Load more documents' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/portal/documents?cursor=signed-cursor', expect.anything())
    expect(screen.getByRole('button', { name: /current guide/i })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /older guide/i })).toBeInTheDocument()
  })

  it('lists own issued invoices and opens matching PDF and CSV downloads', async () => {
    const invoice = { id: 'invoice-1', state: 'issued', number: 'INV-000001', currency: 'USD', invoice_date: '2026-08-29', due_date: '2026-09-28', reference: 'PO-1', notes: '', subtotal: '25.00', tax_total: '0.00', total: '25.00', bill_to: { legal_name: 'Example Client, LLC', contact_name: 'Morgan Lee', billing_email: 'accounts@example.invalid', phone: '512-555-0144', address_line_1: '400 Congress Avenue', address_line_2: 'Suite 900', city: 'Austin', region: 'TX', postal_code: '78701', country_code: 'US' }, lines: [{ id: 'line-1', position: 1, description: 'Managed service', quantity: '1.000', unit: 'hour', unit_amount: '25.00', currency: 'USD', tax_rate_name: '', tax_rate_value: '0.000000', tax_inclusive: false, net: '25.00', tax: '0.00', total: '25.00', origin_type: '', origin_id: null }], created_at: '2026-08-29T12:00:00Z', updated_at: '2026-08-29T12:00:00Z', issued_at: '2026-08-29T12:00:00Z' }
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/api/v1/portal/invoices')) return Promise.resolve(new Response(JSON.stringify({ count: 1, results: [invoice] }), { status: 200 }))
      if (url.endsWith('/api/v1/portal/invoices/invoice-1')) return Promise.resolve(new Response(JSON.stringify(invoice), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ count: 0, has_more: false, next_cursor: null, results: [] }), { status: 200 }))
    })
    const user = userEvent.setup()
    renderPortal('/portal?section=invoices')

    await user.click(await screen.findByRole('button', { name: /INV-000001/i }))
    expect(await screen.findByRole('heading', { name: 'INV-000001' })).toBeInTheDocument()
    expect(screen.getByText('Managed service')).toBeInTheDocument()
    expect(screen.getByText('1.000 hour × USD 25.00')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Bill to' })).toBeInTheDocument()
    expect(screen.getByText('Morgan Lee')).toBeInTheDocument()
    expect(screen.getByText('400 Congress Avenue')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download PDF' })).toHaveAttribute('href', '/api/v1/portal/invoices/invoice-1/pdf')
    expect(screen.getByRole('link', { name: 'Download CSV' })).toHaveAttribute('href', '/api/v1/portal/invoices/invoice-1/csv')
  })

  it('explains a due review and labels downloadable items as files', async () => {
    const publication = { id: 'pub-review', title: 'Password guide', category: 'guide', reason: 'Approved', lifecycle_state: 'review_due', retention: 'review_on', retention_review_on: '2026-08-01', published_at: '2026-07-01T12:00:00Z', content_digest: 'review', source_kind: 'organization_document', visibility: 'client_visible', artifacts: [{ id: 'file-1', kind: 'pdf', filename: 'password-guide.pdf', size: 2400, checksum: 'abc' }] }
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/api/v1/portal/invoices')) return Promise.resolve(new Response(JSON.stringify({ count: 0, results: [] }), { status: 200 }))
      if (url.endsWith('/api/v1/portal/documents')) return Promise.resolve(new Response(JSON.stringify({ count: 1, has_more: false, next_cursor: null, results: [publication] }), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ ...publication, sanitized_html: '<p>Use a password manager.</p>' }), { status: 200 }))
    })
    const user = userEvent.setup()
    renderPortal()

    await user.click(await screen.findByRole('button', { name: /Password guide/i }))
    expect(await screen.findByText('This document is due for review, but you can still use it.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Files' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'password-guide.pdf' })).toHaveAttribute('href', '/api/v1/portal/documents/pub-review/artifacts/file-1/download')
  })

  it('does not disclose a document or invoice that is no longer available', async () => {
    const document = { id: 'pub-withdrawn', title: 'Old guide', category: 'guide', reason: '', lifecycle_state: 'published', retention: 'permanent', retention_review_on: null, published_at: '2026-07-01T12:00:00Z', content_digest: 'old', source_kind: 'organization_document', visibility: 'client_visible', artifacts: [] }
    const invoice = { id: 'invoice-old', state: 'issued', number: 'INV-OLD', currency: 'USD', invoice_date: '2026-08-29', due_date: '2026-09-28', reference: '', notes: '', subtotal: '25.00', tax_total: '0.00', total: '25.00', lines: [], created_at: '2026-08-29T12:00:00Z', updated_at: '2026-08-29T12:00:00Z', issued_at: '2026-08-29T12:00:00Z' }
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/api/v1/portal/documents')) return Promise.resolve(new Response(JSON.stringify({ count: 1, has_more: false, next_cursor: null, results: [document] }), { status: 200 }))
      if (url.endsWith('/api/v1/portal/invoices')) return Promise.resolve(new Response(JSON.stringify({ count: 1, has_more: false, next_cursor: null, results: [invoice] }), { status: 200 }))
      return Promise.resolve(new Response('', { status: 404 }))
    })
    const user = userEvent.setup()
    renderPortal()

    await user.click(await screen.findByRole('button', { name: /Old guide/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('This document is no longer available.')
    await user.click(screen.getByRole('link', { name: 'Invoices' }))
    await user.click(screen.getByRole('button', { name: /INV-OLD/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('This invoice is no longer available.')
    expect(screen.queryByText(/Portal access was denied|Published documentation/)).not.toBeInTheDocument()
  })

  it('offers a useful retry when the portal lists cannot be loaded', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('private server detail'))
    const user = userEvent.setup()
    renderPortal()

    const documentSection = screen.getByRole('heading', { name: 'Documents' }).closest('section')
    if (!documentSection) throw new Error('Document section was not rendered.')
    expect(await within(documentSection).findByRole('alert')).toHaveTextContent('Try again. If the problem continues, contact your MSP.')
    expect(screen.queryByText('private server detail')).not.toBeInTheDocument()

    fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ count: 0, has_more: false, next_cursor: null, results: [] }), { status: 200 })))
    await user.click(within(documentSection).getByRole('button', { name: 'Try again' }))
    expect(await within(documentSection).findByText('No documents have been shared with your organization.')).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Invoices' }))
    expect(await screen.findByText('No invoices have been issued to your organization.')).toBeInTheDocument()
  })

  it('loads one addressable portal section at a time and restores direct detail links', async () => {
    const document = { id: 'pub-1', title: 'Direct guide', category: 'guide', reason: '', lifecycle_state: 'published', retention: 'permanent', retention_review_on: null, published_at: '2026-07-01T12:00:00Z', content_digest: 'direct', source_kind: 'organization_document', visibility: 'client_visible', artifacts: [] }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/api/v1/portal/documents/pub-1')) return Promise.resolve(new Response(JSON.stringify({ ...document, sanitized_html: '<p>Direct content</p>' }), { status: 200 }))
      if (url.endsWith('/api/v1/portal/documents')) return Promise.resolve(new Response(JSON.stringify({ count: 1, has_more: false, next_cursor: null, results: [document] }), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ count: 0, has_more: false, next_cursor: null, results: [] }), { status: 200 }))
    })

    renderPortal('/portal?section=documents&document=pub-1')

    expect(await screen.findByText('Direct content')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      return url.includes('/portal/invoices')
    })).toBe(false)
    await userEvent.click(screen.getByRole('link', { name: 'Invoices' }))
    expect(await screen.findByText('No invoices have been issued to your organization.')).toBeInTheDocument()
  })

  it('opens a direct repository publication with sanitized content and retained downloads', async () => {
    const publication = { id: 'repo-1', content_id: 'document-1', title: 'Laptop setup', created_at: '2026-10-08T12:00:00Z' }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/api/v1/portal/repository-publications/repo-1')) return Promise.resolve(new Response(JSON.stringify({
        ...publication,
        rendered_html: '<h3>Setup steps</h3><script>alert(1)</script>',
        attachments: [{ id: 'artifact-1', filename: 'enrollment.txt', media_type: 'text/plain', size: 128 }],
      }), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ count: 1, has_more: false, next_cursor: null, results: [publication] }), { status: 200 }))
    })
    const { container } = renderPortal('/portal?section=publications&publication=repo-1')

    expect(await screen.findByRole('heading', { name: 'Setup steps' })).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    expect(screen.getByRole('link', { name: 'Download PDF' })).toHaveAttribute('href', '/api/v1/portal/repository-publications/repo-1/pdf')
    expect(screen.getByRole('link', { name: 'enrollment.txt' })).toHaveAttribute('href', '/api/v1/portal/repository-publications/repo-1/attachments/artifact-1')
    expect(fetchMock.mock.calls.every(([input]) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      return url.includes('/portal/repository-publications')
    })).toBe(true)
  })

  it('pages new publications independently of legacy documents', async () => {
    const publication = (id: string, title: string) => ({ id, content_id: id, title, created_at: '2026-10-08T12:00:00Z' })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.includes('cursor=')) return Promise.resolve(new Response(JSON.stringify({ count: 1, has_more: false, next_cursor: null, results: [publication('repo-2', 'Older setup')] }), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ count: 1, has_more: true, next_cursor: 'repo-cursor', results: [publication('repo-1', 'Current setup')] }), { status: 200 }))
    })
    renderPortal('/portal?section=publications')

    await userEvent.click(await screen.findByRole('button', { name: 'Load more publications' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/portal/repository-publications?cursor=repo-cursor', expect.anything())
    expect(screen.getByRole('button', { name: /current setup/i })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /older setup/i })).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      return url.includes('/portal/documents')
    })).toBe(false)
  })

  it('keeps an unavailable repository publication out of the reader and offers list retry', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/repo-withdrawn')) return Promise.resolve(new Response('', { status: 404 }))
      return Promise.reject(new Error('private repository detail'))
    })
    renderPortal('/portal?section=publications&publication=repo-withdrawn')
    const section = screen.getByRole('heading', { name: 'New publications' }).closest('section')
    if (!section) throw new Error('Publication section was not rendered.')
    expect(await screen.findByText('This document is no longer available. Return to the document list and try again.')).toBeInTheDocument()
    expect(await within(section).findByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.queryByText('private repository detail')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Download PDF' })).not.toBeInTheDocument()

    fetchMock.mockResolvedValue(new Response(JSON.stringify({ count: 0, has_more: false, next_cursor: null, results: [] }), { status: 200 }))
    await userEvent.click(within(section).getByRole('button', { name: 'Try again' }))
    expect(await within(section).findByText('No new publications have been shared with your organization.')).toBeInTheDocument()
  })

  it('does not reuse a previously opened publication after access is revoked', async () => {
    const publication = { id: 'repo-revoked', content_id: 'document-2', title: 'Enrollment guide', created_at: '2026-10-08T12:00:00Z' }
    let available = true
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/repo-revoked')) return Promise.resolve(available
        ? new Response(JSON.stringify({ ...publication, rendered_html: '<p>Retained instructions</p>', attachments: [] }), { status: 200 })
        : new Response('', { status: 404 }))
      return Promise.resolve(new Response(JSON.stringify({ count: 1, has_more: false, next_cursor: null, results: [publication] }), { status: 200 }))
    })
    const user = userEvent.setup()
    renderPortal('/portal?section=publications')

    await user.click(await screen.findByRole('button', { name: /Enrollment guide/i }))
    expect(await screen.findByText('Retained instructions')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'All new publications' }))
    available = false
    await user.click(await screen.findByRole('button', { name: /Enrollment guide/i }))
    expect(await screen.findByText('This document is no longer available. Return to the document list and try again.')).toBeInTheDocument()
    expect(screen.queryByText('Retained instructions')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Download PDF' })).not.toBeInTheDocument()
  })
})
