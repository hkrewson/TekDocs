import { render, screen, within } from '@testing-library/react'
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
  mfa_enrollment_required: false,
}

afterEach(() => vi.restoreAllMocks())

describe('ClientPortal', () => {
  it('provides direct keyboard access to the portal content', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ count: 0, has_more: false, next_cursor: null, results: [] }), { status: 200 }))
    render(<ClientPortal context={context} onSignOut={vi.fn()} signingOut={false} signOutError={null} />)

    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveAttribute('href', '#portal-main-content')
    expect(screen.getByRole('main')).toHaveAttribute('id', 'portal-main-content')
  })

  it('lists and opens a document without exposing publication internals', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/api/v1/portal/invoices')) return Promise.resolve(new Response(JSON.stringify({ count: 0, results: [] }), { status: 200 }))
      if (url.endsWith('/api/v1/portal/documents')) return Promise.resolve(new Response(JSON.stringify({ count: 1, has_more: false, next_cursor: null, results: [{ id: 'pub-1', title: 'Access guide', category: 'guide', reason: 'Approved', lifecycle_state: 'published', retention: 'permanent', retention_review_on: null, published_at: '2026-08-11T12:00:00Z', content_digest: 'abc', source_kind: 'organization_document', visibility: 'client_visible', artifacts: [] }] }), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ id: 'pub-1', title: 'Access guide', category: 'guide', reason: 'Approved', lifecycle_state: 'published', retention: 'permanent', retention_review_on: null, published_at: '2026-08-11T12:00:00Z', content_digest: 'abc', source_kind: 'organization_document', visibility: 'client_visible', artifacts: [], sanitized_html: '<h1>Safe guide</h1><script>alert(1)</script>' }), { status: 200 }))
    })
    const { container } = render(<ClientPortal context={context} onSignOut={vi.fn()} signingOut={false} signOutError={null} />)
    expect(await screen.findByRole('button', { name: /access guide/i })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /access guide/i }))
    expect(await screen.findByRole('heading', { name: 'Safe guide' })).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    expect(screen.getByRole('button', { name: /all documents/i })).toBeInTheDocument()
    expect(screen.queryByText(/STATIC|Client visible/)).not.toBeInTheDocument()
  })

  it('shows a clear empty state without exposing MSP navigation', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ count: 0, has_more: false, next_cursor: null, results: [] }), { status: 200 }))
    render(<ClientPortal context={context} onSignOut={vi.fn()} signingOut={false} signOutError={null} />)
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
    render(<ClientPortal context={context} onSignOut={vi.fn()} signingOut={false} signOutError={null} />)

    await user.click(await screen.findByRole('button', { name: 'Load more documents' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/portal/documents?cursor=signed-cursor', expect.anything())
    expect(screen.getByRole('button', { name: /current guide/i })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /older guide/i })).toBeInTheDocument()
  })

  it('lists own issued invoices and opens matching PDF and CSV downloads', async () => {
    const invoice = { id: 'invoice-1', state: 'issued', number: 'INV-000001', currency: 'USD', invoice_date: '2026-08-29', due_date: '2026-09-28', reference: 'PO-1', notes: '', subtotal: '25.00', tax_total: '0.00', total: '25.00', lines: [{ id: 'line-1', position: 1, description: 'Managed service', quantity: '1.000', unit_amount: '25.00', currency: 'USD', tax_rate_name: '', tax_rate_value: '0.000000', tax_inclusive: false, net: '25.00', tax: '0.00', total: '25.00', origin_type: '', origin_id: null }], created_at: '2026-08-29T12:00:00Z', updated_at: '2026-08-29T12:00:00Z', issued_at: '2026-08-29T12:00:00Z' }
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/api/v1/portal/invoices')) return Promise.resolve(new Response(JSON.stringify({ count: 1, results: [invoice] }), { status: 200 }))
      if (url.endsWith('/api/v1/portal/invoices/invoice-1')) return Promise.resolve(new Response(JSON.stringify(invoice), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ count: 0, has_more: false, next_cursor: null, results: [] }), { status: 200 }))
    })
    const user = userEvent.setup()
    render(<ClientPortal context={context} onSignOut={vi.fn()} signingOut={false} signOutError={null} />)

    await user.click(await screen.findByRole('button', { name: /INV-000001/i }))
    expect(await screen.findByRole('heading', { name: 'INV-000001' })).toBeInTheDocument()
    expect(screen.getByText('Managed service')).toBeInTheDocument()
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
    render(<ClientPortal context={context} onSignOut={vi.fn()} signingOut={false} signOutError={null} />)

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
    render(<ClientPortal context={context} onSignOut={vi.fn()} signingOut={false} signOutError={null} />)

    await user.click(await screen.findByRole('button', { name: /Old guide/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('This document is no longer available.')
    await user.click(screen.getByRole('button', { name: /INV-OLD/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('This invoice is no longer available.')
    expect(screen.queryByText(/Portal access was denied|Published documentation/)).not.toBeInTheDocument()
  })

  it('offers a useful retry when the portal lists cannot be loaded', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('private server detail'))
    const user = userEvent.setup()
    render(<ClientPortal context={context} onSignOut={vi.fn()} signingOut={false} signOutError={null} />)

    const invoiceSection = screen.getByRole('heading', { name: 'Invoices' }).closest('section')
    const documentSection = screen.getByRole('heading', { name: 'Documents' }).closest('section')
    if (!invoiceSection || !documentSection) throw new Error('Portal sections were not rendered.')
    expect(await within(invoiceSection).findByRole('alert')).toHaveTextContent('Try again. If the problem continues, contact your MSP.')
    expect(screen.queryByText('private server detail')).not.toBeInTheDocument()

    fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ count: 0, has_more: false, next_cursor: null, results: [] }), { status: 200 })))
    await user.click(within(invoiceSection).getByRole('button', { name: 'Try again' }))
    await user.click(within(documentSection).getByRole('button', { name: 'Try again' }))
    expect(await within(invoiceSection).findByText('No invoices have been issued to your organization.')).toBeInTheDocument()
    expect(await within(documentSection).findByText('No documents have been shared with your organization.')).toBeInTheDocument()
  })
})
