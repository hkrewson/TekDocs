import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { DocumentRecord, DocumentsClient } from '../documentation/api'
import { Files } from './Files'

const document: DocumentRecord = {
  id: 'document-1', title: 'Firewall guide', owner_kind: 'msp', owner_organization_id: null, owner_organization_name: null,
  is_reference: false, category: 'guide', is_template: false, library_visible: false, template_enrollment_id: null,
  template_applied_revision_id: null, template_source_id: null, markdown: '# Firewall', block_id: 'block-1',
  current_revision_id: 'revision-1', revision_number: 1, checksum: 'a'.repeat(64), resolved_markdown: '# Firewall',
  placements: [], placement_count: 0, publications: [], publication_count: 0, created_at: '2026-08-28T12:00:00Z',
  updated_at: '2026-08-28T12:00:00Z', attachment_count: 1,
  primary_file: null, primary_file_versions: [],
  attachments: [{ id: 'file-1', filename: 'firewall-runbook.pdf', media_type: 'application/pdf', size: 2048, checksum: 'b'.repeat(64), scan_status: 'clean', scan_engine: 'scanner', scanned_at: '2026-08-28T12:00:00Z', created_at: '2026-08-28T12:00:00Z' }],
}

describe('Files', () => {
  it('lists authorized document files with download and owning-document links', async () => {
    const client = {
      list: vi.fn().mockResolvedValue({ results: [document], count: 1 }),
      attachmentDownloadUrl: vi.fn().mockReturnValue('/api/files/file-1/download'),
    } as unknown as DocumentsClient
    render(<MemoryRouter initialEntries={['/files?q=firewall']}><Files workspace={null} client={client} /></MemoryRouter>)

    expect(await screen.findByText('firewall-runbook.pdf')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Firewall guide/ })).toHaveAttribute('href', '/documentation?document=document-1')
    expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute('href', '/api/files/file-1/download')
    expect(screen.getByRole('table', { name: 'Managed files' })).toBeInTheDocument()
  })

  it('shows a truthful empty state when documents have no files', async () => {
    const client = { list: vi.fn().mockResolvedValue({ results: [{ ...document, attachments: [], attachment_count: 0 }], count: 1 }) } as unknown as DocumentsClient
    render(<MemoryRouter><Files workspace={null} client={client} /></MemoryRouter>)
    expect(await screen.findByText('No managed files are attached to documents in this workspace.')).toBeInTheDocument()
  })
})
