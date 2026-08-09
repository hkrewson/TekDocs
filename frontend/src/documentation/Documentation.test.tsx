import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

vi.mock('../editor/EditorSpike', () => ({
  EditorSpike: ({ initialMarkdown, onMarkdownChange }: { initialMarkdown: string; onMarkdownChange: (value: string) => void }) => <textarea aria-label="Document Markdown" defaultValue={initialMarkdown} onChange={(event) => onMarkdownChange(event.target.value)} />,
}))

import { Documentation } from './Documentation'
import { RevisionConflictError } from './api'
import type { DocumentInput, DocumentRecord, DocumentUpdateInput, DocumentsClient } from './api'
import type { WorkspaceClient } from '../workspaces/api'

const primaryPlacement = { id: 'placement-1', parent_id: null, block_id: 'block-1', block_name: 'Firewall standard — content', position: 0, depth: 0, resolution_mode: 'live' as const, pinned_revision_id: null, resolved_revision_id: 'revision-1', resolved_revision_number: 1, resolved_checksum: 'abc123', is_primary: true }
const document: DocumentRecord = { id: 'doc-1', title: 'Firewall standard', owner_kind: 'msp', owner_organization_id: null, owner_organization_name: null, is_reference: false, markdown: '# Firewall', block_id: 'block-1', current_revision_id: 'revision-1', revision_number: 1, checksum: 'abc123', resolved_markdown: '# Firewall\n', placements: [primaryPlacement], placement_count: 1, created_at: '2026-08-09T00:00:00Z', updated_at: '2026-08-09T00:00:00Z' }
const sourceDocument: DocumentRecord = { ...document, id: 'doc-source', title: 'Shared checklist', block_id: 'block-source', current_revision_id: 'revision-source', placements: [{ ...primaryPlacement, id: 'placement-source', block_id: 'block-source', block_name: 'Shared checklist — content', resolved_revision_id: 'revision-source' }] }

function clients() {
  const createDocument = vi.fn((_scope: object, input: DocumentInput) => Promise.resolve({ ...document, ...input, id: 'doc-2' }))
  const updateDocument = vi.fn((_scope: object, _id: string, input: DocumentUpdateInput) => Promise.resolve({ ...document, ...input, current_revision_id: 'revision-2', revision_number: 2 }))
  const addReference = vi.fn(() => Promise.resolve())
  const reusedPlacement = { ...sourceDocument.placements[0], id: 'placement-reused', is_primary: false }
  const composed = { ...document, resolved_markdown: '# Firewall\n\nShared content\n', placements: [primaryPlacement, reusedPlacement], placement_count: 2 }
  const addPlacement = vi.fn(() => Promise.resolve(composed))
  const updatePlacement = vi.fn(() => Promise.resolve({ ...composed, placements: [primaryPlacement, { ...reusedPlacement, resolution_mode: 'pinned' as const, pinned_revision_id: 'revision-source' }] }))
  const removePlacement = vi.fn(() => Promise.resolve(document))
  const documents: DocumentsClient = {
    list: vi.fn().mockResolvedValue({ results: [document, sourceDocument], count: 2 }),
    create: createDocument,
    update: updateDocument,
    listRevisions: vi.fn().mockResolvedValue({ results: [{ id: 'revision-1', parent_id: null, revision_number: 1, checksum: 'abc123', created_by: 'Primary Owner', created_at: '2026-08-09T00:00:00Z', is_current: true }], count: 1 }),
    getRevision: vi.fn().mockResolvedValue({ id: 'revision-1', parent_id: null, revision_number: 1, checksum: 'abc123', created_by: 'Primary Owner', created_at: '2026-08-09T00:00:00Z', is_current: true, markdown: '# Firewall', diff_from_parent: '+# Firewall' }),
    addPlacement,
    updatePlacement,
    removePlacement,
    archive: vi.fn().mockResolvedValue(undefined),
    addReference,
  }
  const workspaces: WorkspaceClient = {
    loadMsp: vi.fn(), loadOrganization: vi.fn(),
    searchOrganizations: vi.fn().mockResolvedValue({ results: [{ id: 'org-1', name: 'Acme', classifications: ['client'], capabilities: ['documentation'] }], page: 1, page_size: 15, has_more: false }),
  }
  return { documents, workspaces, createDocument, updateDocument, addReference, addPlacement, updatePlacement, removePlacement }
}

it('lists titles and persists edited Markdown', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, updateDocument } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.clear(await screen.findByRole('textbox', { name: 'Document Markdown' }))
  await user.type(screen.getByRole('textbox', { name: 'Document Markdown' }), '# Updated')
  await user.click(screen.getByRole('button', { name: 'Save document' }))
  await waitFor(() => expect(updateDocument).toHaveBeenCalledWith({}, 'doc-1', { title: 'Firewall standard', markdown: '# Updated', base_revision_id: 'revision-1' }))
  expect(screen.getByRole('status')).toHaveTextContent('Document saved as revision 2.')
})

it('loads revision history and a selected diff', async () => {
  const user = userEvent.setup()
  const { documents, workspaces } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(screen.getByRole('button', { name: 'Revision history' }))
  await user.click(await screen.findByRole('button', { name: /Revision 1/ }))
  expect(await screen.findByText('+# Firewall')).toBeInTheDocument()
})

it('keeps the draft visible when a stale revision is rejected', async () => {
  const user = userEvent.setup()
  const { documents, workspaces } = clients()
  documents.update = vi.fn().mockRejectedValue(new RevisionConflictError({
    code: 'revision_conflict', detail: 'Changed', submitted_base_revision_id: 'revision-1',
    current_revision: { id: 'revision-2', parent_id: 'revision-1', revision_number: 2, checksum: 'def456', created_by: 'Other editor', created_at: '2026-08-09T01:00:00Z', is_current: true, markdown: '# Server edit', diff_from_parent: '-# Firewall\n+# Server edit' },
    diff: '-# Firewall\n+# Server edit',
  }))
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  const editor = await screen.findByRole('textbox', { name: 'Document Markdown' })
  await user.clear(editor); await user.type(editor, '# My unsaved draft')
  await user.click(screen.getByRole('button', { name: 'Save document' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Newer revision detected')
  expect(editor).toHaveValue('# My unsaved draft')
  expect(screen.getByText(/Server edit/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Save document' })).toBeDisabled()
})

it('creates a document and adds an MSP-owned reference to a searched client', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, createDocument, addReference } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await screen.findByRole('button', { name: /Firewall standard/ })
  await user.click(screen.getByRole('button', { name: 'New document' }))
  await user.type(screen.getByLabelText('Document title'), 'New guide')
  await user.type(screen.getByRole('textbox', { name: 'Document Markdown' }), 'Portable Markdown')
  await user.click(screen.getByRole('button', { name: 'Save document' }))
  await waitFor(() => expect(createDocument).toHaveBeenCalledWith({}, { title: 'New guide', markdown: 'Portable Markdown' }))
  await user.type(screen.getByRole('searchbox', { name: 'Find client organization' }), 'Acm')
  await user.click(await screen.findByRole('button', { name: /Acme/ }))
  expect(addReference).toHaveBeenCalledWith('doc-2', 'org-1')
})

it('adds a visible document block live and can pin its resolved revision', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, addPlacement, updatePlacement } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.selectOptions(screen.getByLabelText('Document block'), 'doc-source')
  await user.click(screen.getByRole('button', { name: 'Add block' }))
  await waitFor(() => expect(addPlacement).toHaveBeenCalledWith({}, 'doc-1', { source_document_id: 'doc-source', resolution_mode: 'live', pinned_revision_id: null }))
  expect(await screen.findByText(/Live · revision 1/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Pin revision' }))
  expect(updatePlacement).toHaveBeenCalledWith({}, 'doc-1', 'placement-reused', { resolution_mode: 'pinned', pinned_revision_id: 'revision-source' })
})
