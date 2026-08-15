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

const primaryPlacement = { id: 'placement-1', parent_id: null, block_id: 'block-1', block_name: 'Firewall standard — content', block_kind: 'rich_text' as const, position: 0, depth: 0, resolution_mode: 'live' as const, pinned_revision_id: null, resolved_revision_id: 'revision-1', resolved_revision_number: 1, resolved_checksum: 'abc123', resolved_markdown: '# Firewall', is_primary: true }
const document: DocumentRecord = { id: 'doc-1', title: 'Firewall standard', owner_kind: 'msp', owner_organization_id: null, owner_organization_name: null, is_reference: false, category: 'policy', is_template: false, library_visible: false, template_enrollment_id: null, template_applied_revision_id: null, template_source_id: null, attachments: [], attachment_count: 0, publications: [], publication_count: 0, markdown: '# Firewall', block_id: 'block-1', current_revision_id: 'revision-1', revision_number: 1, checksum: 'abc123', resolved_markdown: '# Firewall\n', placements: [primaryPlacement], placement_count: 1, created_at: '2026-08-09T00:00:00Z', updated_at: '2026-08-09T00:00:00Z' }
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
  const getReuseImpact = vi.fn().mockResolvedValue({ block_id: 'block-1', block_name: 'Firewall standard — content', revision_id: 'revision-1', revision_number: 1, checksum: 'abc123', markdown: '# Firewall', audiences: [], live_audience_count: 1, pinned_audience_count: 0, can_edit_shared: true, can_detach: false, requires_mfa: true, truncated: false })
  const updateSharedBlock = vi.fn().mockResolvedValue(document)
  const detachPlacement = vi.fn().mockResolvedValue(document)
  const searchMentionEntities = vi.fn().mockResolvedValue({ results: [], count: 0, has_more: false })
  const searchBlockLibrary = vi.fn().mockResolvedValue({ results: [], count: 0 })
  const instantiateTemplate = vi.fn().mockResolvedValue({ ...document, id: 'doc-from-template', title: 'New from Firewall standard', is_template: false })
  const importMarkdown = vi.fn().mockResolvedValue({ ...document, id: 'doc-imported', title: 'imported', category: 'general' })
  const uploadAttachment = vi.fn().mockResolvedValue({ id: 'attachment-1', filename: 'notes.txt', media_type: 'text/plain', size: 5, checksum: 'checksum', scan_status: 'clean', scan_engine: 'test-scanner', scanned_at: '2026-08-09T00:00:00Z', created_at: '2026-08-09T00:00:00Z' })
  const archiveAttachment = vi.fn().mockResolvedValue(undefined)
  const publication = { id: 'publication-1', source_document_id: 'doc-1', title: 'Firewall standard', category: 'policy' as const, reason: 'Approved for operations', audience: 'msp_internal' as const, retention: 'permanent' as const, retention_review_on: null, lifecycle_state: 'published' as const, supersedes_id: null, superseded_by_id: null, control_events: [{ id: 'event-1', action: 'submitted' as const, reason: 'Approved for operations', actor: 'Primary Owner', occurred_at: '2026-08-09T01:00:00Z' }, { id: 'event-2', action: 'approved' as const, reason: 'Approved for MSP-internal distribution at publication time.', actor: 'Primary Owner', occurred_at: '2026-08-09T01:00:00Z' }], audience_projections: [{ audience: 'msp_staff' as const, available: true, state: 'retained' }, { audience: 'client_portal' as const, available: false, state: 'not_intended' }], artifacts: [{ id: 'pdf-1', kind: 'pdf' as const, filename: 'firewall-static.pdf', media_type: 'application/pdf', size: 1200, checksum: 'c'.repeat(64), source_attachment_id: null }], content_digest: 'a'.repeat(64), signature_algorithm: 'Ed25519' as const, signature: 'signature', public_key: 'public-key', key_fingerprint: 'b'.repeat(64), published_by: 'Primary Owner', published_at: '2026-08-09T01:00:00Z', verification: { valid: true, digest_valid: true, signature_valid: true, key_fingerprint_valid: true }, canonical_markdown: '# Firewall\n', sanitized_html: '<h1>Firewall</h1>', manifest: { format: 'tekdocs-static-publication/v2' } }
  const publish = vi.fn().mockResolvedValue(publication)
  const approvePublication = vi.fn().mockResolvedValue(publication)
  const withdrawPublication = vi.fn().mockResolvedValue({ ...publication, lifecycle_state: 'withdrawn' as const })
  const getPublication = vi.fn().mockResolvedValue(publication)
  const saveRemoteSource = vi.fn().mockResolvedValue({ id: 'source-1', url: 'https://docs.example.invalid/setup', source_kind: 'auto', enabled: true, check_interval_minutes: 1440, next_check_at: '2026-08-16T00:00:00Z', last_checked_at: null, last_applied_observation_id: null })
  const checkRemoteSource = vi.fn().mockResolvedValue({ id: 'observation-1', state: 'changed', status_code: 200, content_type: 'text/markdown', content_digest: 'a'.repeat(64), error_code: '', fetched_at: '2026-08-15T00:00:00Z', canonical_markdown: '# Setup\n', diff: '+# Setup' })
  const applyRemoteObservation = vi.fn().mockResolvedValue({ id: 'observation-1', state: 'changed', status_code: 200, content_type: 'text/markdown', content_digest: 'a'.repeat(64), error_code: '', fetched_at: '2026-08-15T00:00:00Z', canonical_markdown: '# Setup\n', diff: '+# Setup' })
  const documents: DocumentsClient = {
    list: vi.fn().mockResolvedValue({ results: [document, sourceDocument], count: 2 }),
    create: createDocument,
    update: updateDocument,
    listRevisions: vi.fn().mockResolvedValue({ results: [{ id: 'revision-1', parent_id: null, revision_number: 1, checksum: 'abc123', created_by: 'Primary Owner', created_at: '2026-08-09T00:00:00Z', is_current: true }], count: 1, page: 1, page_size: 50, has_more: false }),
    getRevision: vi.fn().mockResolvedValue({ id: 'revision-1', parent_id: null, revision_number: 1, checksum: 'abc123', created_by: 'Primary Owner', created_at: '2026-08-09T00:00:00Z', is_current: true, markdown: '# Firewall', diff_from_parent: '+# Firewall' }),
    addPlacement,
    updatePlacement,
    removePlacement,
    getReuseImpact,
    updateSharedBlock,
    detachPlacement,
    searchMentionEntities,
    searchBlockLibrary,
    listTemplateLibrary: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    instantiateTemplate,
    previewTemplateRollout: vi.fn().mockResolvedValue({ enrollment_id: 'enrollment-1', applied_revision_id: 'template-revision-1', current_revision: 1, available_revision: 1, up_to_date: true, added: [], changed: [], removed: [], conflicts: [] }),
    applyTemplateRollout: vi.fn().mockResolvedValue({ enrollment_id: 'enrollment-1', applied_revision_id: 'template-revision-1', current_revision: 1, available_revision: 1, up_to_date: true, added: [], changed: [], removed: [], conflicts: [] }),
    getRemoteSource: vi.fn().mockResolvedValue(undefined),
    saveRemoteSource,
    listRemoteObservations: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    checkRemoteSource,
    applyRemoteObservation,
    importMarkdown,
    uploadAttachment,
    archiveAttachment,
    publish,
    approvePublication,
    withdrawPublication,
    getPublication,
    publicationMarkdownUrl: (_scope, id, publicationId) => `/documents/${id}/publications/${publicationId}/markdown`,
    publicationManifestUrl: (_scope, id, publicationId) => `/documents/${id}/publications/${publicationId}/manifest`,
    publicationArtifactUrl: (_scope, id, publicationId, artifactId) => `/documents/${id}/publications/${publicationId}/artifacts/${artifactId}/download`,
    exportUrl: (_scope, id) => `/documents/${id}/export`,
    attachmentDownloadUrl: (_scope, id, attachmentId) => `/documents/${id}/attachments/${attachmentId}/download`,
    archive: vi.fn().mockResolvedValue(undefined),
    addReference,
  }
  const workspaces: WorkspaceClient = {
    loadMsp: vi.fn(), loadOrganization: vi.fn(),
    searchOrganizations: vi.fn().mockResolvedValue({ results: [{ id: 'org-1', name: 'Acme', classifications: ['client'], capabilities: ['documentation'] }], page: 1, page_size: 15, has_more: false }),
  }
  return { documents, workspaces, createDocument, updateDocument, addReference, addPlacement, updatePlacement, removePlacement, getReuseImpact, updateSharedBlock, detachPlacement, searchMentionEntities, searchBlockLibrary, instantiateTemplate, importMarkdown, uploadAttachment, archiveAttachment, publish, approvePublication, withdrawPublication, getPublication, saveRemoteSource, checkRemoteSource, applyRemoteObservation, publication }
}

it('lists titles and persists an independently edited block', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, updateSharedBlock } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(screen.getByRole('button', { name: /Firewall standard.*Edit block/ }))
  await user.clear(await screen.findByRole('textbox', { name: 'Document Markdown' }))
  await user.type(screen.getByRole('textbox', { name: 'Document Markdown' }), '# Updated')
  await user.click(screen.getByRole('button', { name: 'Save block' }))
  await waitFor(() => expect(updateSharedBlock).toHaveBeenCalledWith({}, 'doc-1', 'placement-1', '# Updated', 'revision-1'))
  expect(screen.getByRole('status')).toHaveTextContent('Block revision saved.')
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

it('navigates large revision histories without loading every revision', async () => {
  const user = userEvent.setup()
  const { documents, workspaces } = clients()
  const listRevisions = vi.fn()
    .mockResolvedValueOnce({ results: [{ id: 'revision-75', parent_id: 'revision-74', revision_number: 75, checksum: 'abc123', created_by: 'Primary Owner', created_at: '2026-08-09T00:00:00Z', is_current: true }], count: 75, page: 1, page_size: 50, has_more: true })
    .mockResolvedValueOnce({ results: [{ id: 'revision-25', parent_id: 'revision-24', revision_number: 25, checksum: 'def456', created_by: 'Primary Owner', created_at: '2026-08-08T00:00:00Z', is_current: false }], count: 75, page: 2, page_size: 50, has_more: false })
  documents.listRevisions = listRevisions
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(screen.getByRole('button', { name: 'Revision history' }))
  expect(await screen.findByText('Showing 1–50 of 75')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Older revisions' }))
  expect(await screen.findByText('Showing 51–75 of 75')).toBeInTheDocument()
  expect(listRevisions).toHaveBeenLastCalledWith({}, 'doc-1', 2)
})

it('keeps the draft visible when a stale revision is rejected', async () => {
  const user = userEvent.setup()
  const { documents, workspaces } = clients()
  documents.updateSharedBlock = vi.fn().mockRejectedValue(new RevisionConflictError({
    code: 'revision_conflict', detail: 'Changed', submitted_base_revision_id: 'revision-1',
    current_revision: { id: 'revision-2', parent_id: 'revision-1', revision_number: 2, checksum: 'def456', created_by: 'Other editor', created_at: '2026-08-09T01:00:00Z', is_current: true, markdown: '# Server edit', diff_from_parent: '-# Firewall\n+# Server edit' },
    diff: '-# Firewall\n+# Server edit',
  }))
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(screen.getByRole('button', { name: /Firewall standard.*Edit block/ }))
  const editor = await screen.findByRole('textbox', { name: 'Document Markdown' })
  await user.clear(editor); await user.type(editor, '# My unsaved draft')
  await user.click(screen.getByRole('button', { name: 'Save block' }))
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
  await waitFor(() => expect(createDocument).toHaveBeenCalledWith({}, { title: 'New guide', markdown: 'Portable Markdown', category: 'general', is_template: false, library_visible: false }))
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
  await user.click(screen.getByRole('button', { name: 'Reuse document block' }))
  await waitFor(() => expect(addPlacement).toHaveBeenCalledWith({}, 'doc-1', { source_document_id: 'doc-source', resolution_mode: 'live', pinned_revision_id: null }))
  expect((await screen.findAllByText('Revision 1')).length).toBeGreaterThanOrEqual(2)
  await user.click(screen.getAllByRole('button', { name: 'Pin' })[0])
  expect(updatePlacement).toHaveBeenCalledWith({}, 'doc-1', 'placement-reused', { resolution_mode: 'pinned', pinned_revision_id: 'revision-source' })
})

it('creates a typed local block at an explicit document position', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, addPlacement } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(screen.getByRole('button', { name: 'New block' }))
  await user.selectOptions(screen.getByLabelText('Block type'), 'heading')
  await user.type(screen.getByLabelText(/Block name/), 'Network assumptions')
  await user.selectOptions(screen.getByLabelText('Insert after'), '1')
  await user.type(screen.getByRole('textbox', { name: 'Document Markdown' }), '## Addressing')
  await user.click(screen.getByRole('button', { name: 'Add block' }))
  await waitFor(() => expect(addPlacement).toHaveBeenCalledWith({}, 'doc-1', {
    operation: 'create_block',
    block_kind: 'heading',
    block_name: 'Network assumptions',
    markdown: '## Addressing',
    position: 1,
    library_visible: false,
  }))
})

it('discovers and reuses an explicitly available MSP block from a client workspace', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, searchBlockLibrary, addPlacement } = clients()
  searchBlockLibrary.mockResolvedValue({
    count: 1,
    results: [{ id: 'block-shared', name: 'Printer isolation rationale', kind: 'rich_text', markdown: 'Printers belong on IoT.', revision_id: 'revision-shared', revision_number: 3, source_document_id: 'doc-source', source_document_title: 'Network design standard', owner_kind: 'msp', owner_organization_id: null }],
  })
  render(<Documentation workspace={{ kind: 'organization', id: 'org-1', name: 'Acme', classifications: ['client'], capabilities: ['documentation'], organization: null }} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  expect(await screen.findByText('Printer isolation rationale')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Reuse live' }))
  await waitFor(() => expect(addPlacement).toHaveBeenCalledWith({ organizationId: 'org-1' }, 'doc-1', {
    operation: 'reuse_block', source_block_id: 'block-shared', resolution_mode: 'live', pinned_revision_id: null,
  }))
})

it('creates a client document from a published template with per-block behavior', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, instantiateTemplate } = clients()
  const template = {
    ...sourceDocument,
    is_template: true,
    library_visible: true,
    placements: [
      sourceDocument.placements[0],
      { ...sourceDocument.placements[0], id: 'placement-template-2', block_id: 'block-template-2', block_name: 'Printer rationale — content', is_primary: false, position: 1 },
    ],
    placement_count: 2,
  }
  documents.listTemplateLibrary = vi.fn().mockResolvedValue({ results: [template], count: 1 })
  render(<Documentation workspace={{ kind: 'organization', id: 'org-1', name: 'Acme', classifications: ['client'], capabilities: ['documentation'], organization: null }} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: 'Use template' }))
  await user.selectOptions(screen.getByLabelText('Printer rationale'), 'live')
  await user.click(screen.getByRole('button', { name: 'Create client document' }))
  await waitFor(() => expect(instantiateTemplate).toHaveBeenCalledWith(
    { organizationId: 'org-1' },
    'doc-source',
    'Acme — Shared checklist',
    'policy',
    { 'block-template-2': 'live' },
  ))
  expect(screen.getByRole('status')).toHaveTextContent('Client document created from a retained template revision.')
})

it('previews and applies a conflict-free client template rollout', async () => {
  const user = userEvent.setup()
  const { documents, workspaces } = clients()
  const enrolled = { ...document, template_enrollment_id: 'enrollment-1', template_applied_revision_id: 'template-revision-1', template_source_id: 'doc-source' }
  documents.list = vi.fn().mockResolvedValue({ results: [enrolled], count: 1 })
  documents.previewTemplateRollout = vi.fn().mockResolvedValue({
    enrollment_id: 'enrollment-1', applied_revision_id: 'template-revision-1', current_revision: 1, available_revision: 2, up_to_date: false,
    added: [{ source_block_id: 'block-new', source_revision_id: 'revision-new', name: 'New standard', kind: 'rich_text', position: 1 }], changed: [], removed: [], conflicts: [],
  })
  const applyTemplateRollout = vi.fn().mockResolvedValue({ enrollment_id: 'enrollment-1', applied_revision_id: 'template-revision-2', current_revision: 2, available_revision: 2, up_to_date: true, added: [], changed: [], removed: [], conflicts: [] })
  documents.applyTemplateRollout = applyTemplateRollout
  render(<Documentation workspace={{ kind: 'organization', id: 'org-1', name: 'Acme', classifications: ['client'], capabilities: ['documentation'], organization: null }} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(screen.getByRole('button', { name: 'Check template updates' }))
  expect(await screen.findByText('Applied revision 1; available revision 2.')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Apply safe changes' }))
  await waitFor(() => expect(applyTemplateRollout).toHaveBeenCalledWith(
    { organizationId: 'org-1' }, 'enrollment-1', 'template-revision-1', { 'block-new': 'copy' },
  ))
  expect(screen.getByRole('status')).toHaveTextContent('Template revision 2 applied.')
})

it('reviews a monitored public source before applying its Markdown', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, saveRemoteSource, checkRemoteSource, applyRemoteObservation } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(screen.getByRole('button', { name: 'Remote source' }))
  await user.type(screen.getByLabelText('Public document URL'), 'https://docs.example.invalid/setup')
  await user.click(screen.getByRole('button', { name: 'Save source' }))
  await waitFor(() => expect(saveRemoteSource).toHaveBeenCalledWith({}, 'doc-1', expect.objectContaining({
    url: 'https://docs.example.invalid/setup', enabled: true,
  })))
  await user.click(screen.getByRole('button', { name: 'Check now' }))
  expect(await screen.findByText('Change detected')).toBeVisible()
  expect(screen.getByText('+# Setup')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Apply reviewed change' }))
  await waitFor(() => expect(checkRemoteSource).toHaveBeenCalledWith({}, 'doc-1'))
  expect(applyRemoteObservation).toHaveBeenCalledWith({}, 'doc-1', 'observation-1')
  expect(screen.getByRole('status')).toHaveTextContent('Reviewed source change applied as a new block revision.')
})

it('reviews shared audiences and detaches a reused block', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, addPlacement, getReuseImpact, detachPlacement } = clients()
  const reusedImpact = { block_id: 'block-source', block_name: 'Shared checklist — content', revision_id: 'revision-source', revision_number: 1, checksum: 'abc123', markdown: 'Shared content', audiences: [{ relationship: 'placement' as const, document_id: 'doc-1', document_title: 'Firewall standard', workspace_kind: 'msp' as const, workspace_id: 'tenant', workspace_name: 'TekDocs MSP', resolution_mode: 'live' as const, will_update: true }], live_audience_count: 1, pinned_audience_count: 0, can_edit_shared: false, can_detach: true, requires_mfa: true, truncated: false }
  getReuseImpact.mockResolvedValue(reusedImpact)
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.selectOptions(screen.getByLabelText('Document block'), 'doc-source')
  await user.click(screen.getByRole('button', { name: 'Reuse document block' }))
  await waitFor(() => expect(addPlacement).toHaveBeenCalled())
  await user.click(screen.getAllByRole('button', { name: 'Reuse impact' })[1])
  expect(await screen.findByRole('heading', { name: 'Reuse impact' })).toBeVisible()
  expect(screen.getByText('Will update')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Detach into this workspace' }))
  expect(detachPlacement).toHaveBeenCalledWith({}, 'doc-1', 'placement-reused')
})

it('imports Markdown and manages a private attachment link', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, importMarkdown, uploadAttachment, archiveAttachment } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await screen.findByRole('button', { name: /Firewall standard/ })
  await user.upload(screen.getByLabelText('Markdown file to import'), new File(['# Imported'], 'imported.md', { type: 'text/markdown' }))
  await waitFor(() => expect(importMarkdown).toHaveBeenCalledWith({}, expect.any(File), 'imported', 'general', false))
  await user.upload(screen.getByLabelText('Attachment file'), new File(['notes'], 'notes.txt', { type: 'text/plain' }))
  await waitFor(() => expect(uploadAttachment).toHaveBeenCalledWith({}, 'doc-imported', expect.any(File)))
  await user.click(screen.getByRole('button', { name: /Firewall standard.*Edit block/ }))
  await user.click(await screen.findByRole('button', { name: 'Insert link' }))
  expect(screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Document Markdown' }).value).toContain('tekdocs://attachment/attachment-1')
  await user.click(screen.getByRole('button', { name: 'Remove notes.txt' }))
  expect(archiveAttachment).toHaveBeenCalledWith({}, 'doc-imported', 'attachment-1')
})

it('offers inline viewing only for clean PDF files', async () => {
  const user = userEvent.setup()
  const { documents, workspaces } = clients()
  documents.list = vi.fn().mockResolvedValue({ results: [{ ...document, attachments: [
    { id: 'pdf-attachment', filename: 'setup.pdf', media_type: 'application/pdf', size: 512, checksum: 'a'.repeat(64), scan_status: 'clean', scan_engine: 'scanner', scanned_at: '2026-08-15T00:00:00Z', created_at: '2026-08-15T00:00:00Z' },
    { id: 'text-attachment', filename: 'notes.txt', media_type: 'text/plain', size: 12, checksum: 'b'.repeat(64), scan_status: 'clean', scan_engine: 'scanner', scanned_at: '2026-08-15T00:00:00Z', created_at: '2026-08-15T00:00:00Z' },
  ], attachment_count: 2 }], count: 1 })
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  expect(screen.getByRole('button', { name: 'View PDF' })).toBeVisible()
  expect(screen.getAllByRole('button', { name: 'Insert link' })).toHaveLength(2)
})

it('publishes and opens an immutable verified STATIC version', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, publish } = clients()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(screen.getByRole('button', { name: 'Publish STATIC' }))
  await user.type(screen.getByLabelText('Publication reason'), 'Approved for operations')
  await user.click(screen.getByRole('button', { name: 'Publish immutable version' }))
  await waitFor(() => expect(publish).toHaveBeenCalledWith({}, 'doc-1', { reason: 'Approved for operations', audience: 'msp_internal', retention: 'permanent', retention_review_on: null, supersedes_id: null }))
  expect(await screen.findByText('Signature verified')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Download PDF' })).toHaveAttribute('href', '/documents/doc-1/publications/publication-1/artifacts/pdf-1/download')
  expect(screen.getByText(`SHA-256 ${'a'.repeat(64)}`)).toBeVisible()
  expect(screen.getByRole('link', { name: 'Download Markdown' })).toHaveAttribute('href', '/documents/doc-1/publications/publication-1/markdown')
  expect(screen.queryByRole('textbox', { name: 'Document Markdown' })).not.toBeInTheDocument()
})

it('shows pending client publication audiences and records an approval decision', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, publication } = clients()
  const pending = {
    ...publication,
    audience: 'client_visible' as const,
    lifecycle_state: 'pending_approval' as const,
    control_events: [publication.control_events[0]],
    audience_projections: [
      { audience: 'msp_staff' as const, available: true, state: 'retained' },
      { audience: 'client_portal' as const, available: false, state: 'pending_approval' },
    ],
  }
  const approved = {
    ...pending,
    lifecycle_state: 'published' as const,
    control_events: publication.control_events,
    audience_projections: [pending.audience_projections[0], { audience: 'client_portal' as const, available: true, state: 'available' }],
  }
  documents.publish = vi.fn().mockResolvedValue(pending)
  const approvePublication = vi.fn().mockResolvedValue(approved)
  documents.approvePublication = approvePublication
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  render(<Documentation workspace={{ kind: 'organization', id: 'org-1', name: 'Acme', classifications: ['client'], capabilities: ['documentation'], organization: null }} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(screen.getByRole('button', { name: 'Publish STATIC' }))
  await user.type(screen.getByLabelText('Publication reason'), 'Client policy release')
  await user.selectOptions(screen.getByLabelText('Audience'), 'client_visible')
  await user.click(screen.getByRole('button', { name: 'Publish immutable version' }))
  expect((await screen.findAllByText('pending approval')).length).toBeGreaterThan(0)
  expect(screen.getByText('Client portal').parentElement).toHaveTextContent('pending approval')
  await user.click(screen.getByRole('button', { name: 'Approve publication' }))
  await user.type(screen.getByLabelText('Decision reason'), 'Independent approval')
  await user.click(screen.getByRole('button', { name: 'Record approval' }))
  await waitFor(() => expect(approvePublication).toHaveBeenCalledWith({ organizationId: 'org-1' }, 'doc-1', 'publication-1', 'Independent approval'))
  expect(await screen.findByText('Publication approved for its intended audience.')).toBeVisible()
  expect(screen.getByText('Client portal').parentElement).toHaveTextContent('Available')
})
