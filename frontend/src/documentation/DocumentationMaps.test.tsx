import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DocumentationMaps } from './DocumentationMaps'

afterEach(() => vi.restoreAllMocks())

describe('DocumentationMaps', () => {
  it('opens an existing hierarchy and exposes revision, review, and baseline controls', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/choices')) return Promise.resolve(new Response(JSON.stringify({ documents: [{ id: 'doc-1', title: 'Recovery', kind: 'document', detail: 'approved', current_revision_id: 'rev-doc-1' }], publications: [], maps: [], owners: [] }), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ count: 1, results: [{ id: 'map-1', title: 'Operations manual', purpose: 'Recover services', map_type: 'operating_manual', audience: 'msp_internal', owner_id: null, owner_name: null, review_state: 'unreviewed', revision_count: 1, current_revision: { id: 'rev-1', revision_number: 1, title: 'Operations manual', purpose: 'Recover services', map_type: 'operating_manual', audience: 'msp_internal', content_digest: 'a'.repeat(64), created_by: 'Owner', created_at: '2026-09-01T00:00:00Z', entries: [{ id: 'entry-1', parent_id: null, position: 0, kind: 'document', label: '', title: 'Recovery', document_id: 'doc-1', document_revision_id: null, publication_id: null, map_id: null, external_url: '' }] }, baselines: [], created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }] }), { status: 200 }))
    })
    const user = userEvent.setup()
    render(<DocumentationMaps workspace={null} onShowDocuments={vi.fn()} />)
    await user.click(await screen.findByRole('button', { name: /operations manual/i }))
    expect(screen.getByRole('heading', { name: 'Contents' })).toBeInTheDocument()
    expect(screen.getByLabelText('Source')).toHaveValue('doc-1')
    expect(screen.getByRole('button', { name: 'Save new revision' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Check & preview' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()
  })

  it('starts a new map and adds an accessible source row', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/choices')) return Promise.resolve(new Response(JSON.stringify({ documents: [], publications: [], maps: [], owners: [] }), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ count: 0, results: [] }), { status: 200 }))
    })
    const user = userEvent.setup()
    render(<DocumentationMaps workspace={null} onShowDocuments={vi.fn()} />)
    await user.click(await screen.findByRole('button', { name: 'New map' }))
    await user.click(screen.getByRole('button', { name: 'Add item' }))
    expect(screen.getByLabelText('Source type')).toHaveValue('document')
    expect(screen.getByLabelText('Source')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Indent' })).toBeDisabled()
  })
})
