import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

vi.mock('../editor/EditorSpike', () => ({
  EditorSpike: ({ initialMarkdown, onMarkdownChange }: { initialMarkdown: string; onMarkdownChange: (value: string) => void }) => <textarea aria-label="Document Markdown" defaultValue={initialMarkdown} onChange={(event) => onMarkdownChange(event.target.value)} />,
}))

import { Documentation } from './Documentation'
import type { DocumentInput, DocumentRecord, DocumentsClient } from './api'
import type { WorkspaceClient } from '../workspaces/api'

const document: DocumentRecord = { id: 'doc-1', title: 'Firewall standard', owner_kind: 'msp', owner_organization_id: null, owner_organization_name: null, is_reference: false, markdown: '# Firewall', block_id: 'block-1', created_at: '2026-08-09T00:00:00Z', updated_at: '2026-08-09T00:00:00Z' }

function clients() {
  const createDocument = vi.fn((_scope: object, input: DocumentInput) => Promise.resolve({ ...document, ...input, id: 'doc-2' }))
  const updateDocument = vi.fn((_scope: object, _id: string, input: DocumentInput) => Promise.resolve({ ...document, ...input }))
  const addReference = vi.fn(() => Promise.resolve())
  const documents: DocumentsClient = {
    list: vi.fn().mockResolvedValue({ results: [document], count: 1 }),
    create: createDocument,
    update: updateDocument,
    archive: vi.fn().mockResolvedValue(undefined),
    addReference,
  }
  const workspaces: WorkspaceClient = {
    loadMsp: vi.fn(), loadOrganization: vi.fn(),
    searchOrganizations: vi.fn().mockResolvedValue({ results: [{ id: 'org-1', name: 'Acme', classifications: ['client'], capabilities: ['documentation'] }], page: 1, page_size: 15, has_more: false }),
  }
  return { documents, workspaces, createDocument, updateDocument, addReference }
}

it('lists titles and persists edited Markdown', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, updateDocument } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.clear(await screen.findByRole('textbox', { name: 'Document Markdown' }))
  await user.type(screen.getByRole('textbox', { name: 'Document Markdown' }), '# Updated')
  await user.click(screen.getByRole('button', { name: 'Save document' }))
  await waitFor(() => expect(updateDocument).toHaveBeenCalledWith({}, 'doc-1', { title: 'Firewall standard', markdown: '# Updated' }))
  expect(screen.getByRole('status')).toHaveTextContent('Document saved.')
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
