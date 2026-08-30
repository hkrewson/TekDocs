export type PortalArtifact = {
  id: string
  kind: 'pdf' | 'attachment'
  filename: string
  size: number
  checksum: string
}

export type PortalDocument = {
  id: string
  title: string
  category: string
  reason: string
  lifecycle_state: 'published' | 'review_due'
  retention: 'permanent' | 'review_on'
  retention_review_on: string | null
  published_at: string
  content_digest: string
  source_kind: 'organization_document'
  visibility: 'client_visible'
  artifacts: PortalArtifact[]
}

export type PortalDocumentDetail = PortalDocument & { sanitized_html: string }

export type PortalDocumentResult = {
  results: PortalDocument[]
  count: number
  has_more: boolean
  next_cursor: string | null
}

export type PortalInvoice = InvoiceDraft & { state: 'issued'; number: string; issued_at: string }
export type PortalInvoiceResult = { results: PortalInvoice[]; count: number; has_more: boolean; next_cursor: string | null }

async function decode<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(response.status === 403 ? 'Portal access was denied.' : 'Published documentation could not be loaded.')
  return response.json() as Promise<T>
}

export const portalClient = {
  async listDocuments(cursor?: string): Promise<PortalDocumentResult> {
    const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''
    return decode(await fetch(`/api/v1/portal/documents${query}`, { credentials: 'same-origin' }))
  },
  async getDocument(id: string): Promise<PortalDocumentDetail> {
    return decode(await fetch(`/api/v1/portal/documents/${id}`, { credentials: 'same-origin' }))
  },
  artifactUrl(documentId: string, artifactId: string): string {
    return `/api/v1/portal/documents/${documentId}/artifacts/${artifactId}/download`
  },
  async listInvoices(cursor?: string): Promise<PortalInvoiceResult> {
    const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''
    return decode(await fetch(`/api/v1/portal/invoices${query}`, { credentials: 'same-origin' }))
  },
  async getInvoice(id: string): Promise<PortalInvoice> {
    return decode(await fetch(`/api/v1/portal/invoices/${encodeURIComponent(id)}`, { credentials: 'same-origin' }))
  },
  invoicePdfUrl(id: string): string {
    return `/api/v1/portal/invoices/${encodeURIComponent(id)}/pdf`
  },
  invoiceCsvUrl(id: string): string {
    return `/api/v1/portal/invoices/${encodeURIComponent(id)}/csv`
  },
}
import type { InvoiceDraft } from '../accounting/api'
