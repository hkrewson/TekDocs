import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

vi.mock('../editor/EditorSpike', () => ({
  EditorSpike: ({ initialMarkdown, onMarkdownChange }: { initialMarkdown: string; onMarkdownChange: (value: string) => void }) => <textarea aria-label="Document Markdown" defaultValue={initialMarkdown} onChange={(event) => onMarkdownChange(event.target.value)} />,
}))

import { Documentation } from './Documentation'
import { RevisionConflictError } from './api'
import type { DocumentInput, DocumentRecord, DocumentUpdateInput, DocumentsClient } from './api'
import type { WorkspaceClient } from '../workspaces/api'

const primaryPlacement = { id: 'placement-1', parent_id: null, block_id: 'block-1', block_name: 'Firewall standard — content', block_kind: 'rich_text' as const, position: 0, depth: 0, resolution_mode: 'live' as const, audience_profile: 'shared' as const, pinned_revision_id: null, resolved_revision_id: 'revision-1', resolved_revision_number: 1, resolved_checksum: 'abc123', resolved_markdown: '# Firewall', resolved_html: '<h1>Firewall</h1>', is_primary: true }
const document: DocumentRecord = { id: 'doc-1', title: 'Firewall standard', owner_kind: 'msp', owner_organization_id: null, owner_organization_name: null, is_reference: false, category: 'policy', is_template: false, library_visible: false, template_enrollment_id: null, template_applied_revision_id: null, template_source_id: null, attachments: [], attachment_count: 0, primary_file: null, primary_file_versions: [], publications: [], publication_count: 0, markdown: '# Firewall', block_id: 'block-1', current_revision_id: 'revision-1', revision_number: 1, checksum: 'abc123', resolved_markdown: '# Firewall\n', placements: [primaryPlacement], placement_count: 1, created_at: '2026-08-09T00:00:00Z', updated_at: '2026-08-09T00:00:00Z' }
const sourceDocument: DocumentRecord = { ...document, id: 'doc-source', title: 'Shared checklist', block_id: 'block-source', current_revision_id: 'revision-source', placements: [{ ...primaryPlacement, id: 'placement-source', block_id: 'block-source', block_name: 'Shared checklist — content', resolved_revision_id: 'revision-source' }] }

function clients() {
  const getDocument = vi.fn().mockResolvedValue(document)
  const createDocument = vi.fn((_scope: object, input: DocumentInput) => Promise.resolve({ ...document, ...input, id: 'doc-2' }))
  const updateDocument = vi.fn((_scope: object, _id: string, input: DocumentUpdateInput) => Promise.resolve({ ...document, ...input, current_revision_id: 'revision-2', revision_number: 2 }))
  const restructurePreview = { eligible: true, base_revision_id: 'revision-1', base_checksum: 'abc123', section_count: 2, sections: [{ position: 0, kind: 'heading' as const, name: 'Firewall standard — Firewall', markdown: '# Firewall', checksum: 'section-1' }, { position: 1, kind: 'rich_text' as const, name: 'Firewall standard — Require MFA', markdown: 'Require MFA.', checksum: 'section-2' }], blockers: [], warnings: [], dependencies: { publication_count: 0, attachment_count: 0, template_managed: false, remote_managed: false, shared_placement_count: 0 } }
  const restructuredDocument = { ...document, markdown: '# Firewall', resolved_markdown: '# Firewall\n\nRequire MFA.\n', placements: [primaryPlacement, { ...primaryPlacement, id: 'placement-2', block_id: 'block-2', block_name: 'Firewall standard — Require MFA', resolved_revision_id: 'revision-section-2', resolved_markdown: 'Require MFA.', resolved_html: '<p>Require MFA.</p>', position: 1, is_primary: false }], placement_count: 2 }
  const previewRestructure = vi.fn().mockResolvedValue(restructurePreview)
  const applyRestructure = vi.fn().mockResolvedValue({ status: 'restructured', section_count: 2, document: restructuredDocument })
  const addReference = vi.fn(() => Promise.resolve())
  const keyBinding = {
    id: 'binding-1',
    name: 'subject',
    target_entity_id: 'entity-1',
    target_display_name: 'Edge firewall',
    target_entity_type: 'client_asset',
    addressable_fields: ['name', 'serial_number'],
    also_bound_by: [{ id: 'doc-2', title: 'Escalation guide' }],
    created_at: '2026-08-15T00:00:00Z',
  }
  const listKeyBindings = vi.fn().mockResolvedValue({ results: [keyBinding], count: 1, addressable_entity_types: ['client_asset', 'network_device'] })
  const declareKeyBinding = vi.fn().mockResolvedValue(keyBinding)
  const archiveKeyBinding = vi.fn(() => Promise.resolve())
  const browseKeyBindings = vi.fn().mockResolvedValue({
    results: [{ id: 'binding-1', name: 'subject', document_id: 'doc-1', document_title: 'Firewall standard', target_entity_id: 'entity-1', target_display_name: 'Edge firewall', target_entity_type: 'client_asset' }],
    count: 1,
    has_more: false,
  })
  const listDocumentKeys = vi.fn().mockResolvedValue({
    results: [{ expression: 'subject.serial_number', state: 'unresolvable', label: 'Serial number', reason: 'empty' }],
    count: 1,
    unresolved_count: 1,
  })
  const reusedPlacement = { ...sourceDocument.placements[0], id: 'placement-reused', is_primary: false }
  const composed = { ...document, resolved_markdown: '# Firewall\n\nShared content\n', placements: [primaryPlacement, reusedPlacement], placement_count: 2 }
  const addPlacement = vi.fn(() => Promise.resolve(composed))
  const updatePlacement = vi.fn(() => Promise.resolve({ ...composed, placements: [primaryPlacement, { ...reusedPlacement, resolution_mode: 'pinned' as const, pinned_revision_id: 'revision-source' }] }))
  const removePlacement = vi.fn(() => Promise.resolve(document))
  const getReuseImpact = vi.fn().mockResolvedValue({ block_id: 'block-1', block_name: 'Firewall standard — content', revision_id: 'revision-1', revision_number: 1, checksum: 'abc123', markdown: '# Firewall', audiences: [], live_audience_count: 1, pinned_audience_count: 0, can_edit_shared: true, can_detach: false, requires_mfa: true, truncated: false })
  const updateSharedBlock = vi.fn().mockResolvedValue(document)
  const detachPlacement = vi.fn().mockResolvedValue(document)
  const searchMentionEntities = vi.fn().mockResolvedValue({
    results: [{ id: 'entity-1', display_name: 'Router A', entity_type: 'client_asset', workspace_label: 'Acme Dental' }],
    count: 1,
    has_more: false,
  })
  const searchBlockLibrary = vi.fn().mockResolvedValue({ results: [], count: 0 })
  const instantiateTemplate = vi.fn().mockResolvedValue({ ...document, id: 'doc-from-template', title: 'New from Firewall standard', is_template: false })
  const importMarkdown = vi.fn().mockResolvedValue({ ...document, id: 'doc-imported', title: 'imported', category: 'general' })
  const uploadAttachment = vi.fn().mockResolvedValue({ id: 'attachment-1', filename: 'notes.txt', media_type: 'text/plain', size: 5, checksum: 'checksum', scan_status: 'clean', scan_engine: 'test-scanner', scanned_at: '2026-08-09T00:00:00Z', created_at: '2026-08-09T00:00:00Z' })
  const primaryFile = { id: 'primary-1', filename: 'runbook.txt', media_type: 'text/plain', size: 512, checksum: 'p'.repeat(64), scan_status: 'clean' as const, scan_engine: 'test-scanner', scanned_at: '2026-08-09T00:00:00Z', created_at: '2026-08-09T00:00:00Z', version_number: 1, replaces_id: null, is_current: true }
  const createFileBacked = vi.fn((_scope: object, input: { title: string; notes: string; category: string; file: File }) => Promise.resolve({ ...document, id: 'doc-file', title: input.title, markdown: input.notes, category: input.category as DocumentRecord['category'], primary_file: primaryFile, primary_file_versions: [primaryFile] }))
  const replacePrimaryFile = vi.fn().mockResolvedValue({ ...primaryFile, id: 'primary-2', filename: 'firewall-v2.pdf', version_number: 2, replaces_id: 'primary-1' })
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
    get: getDocument,
    create: createDocument,
    createFileBacked,
    update: updateDocument,
    previewRestructure,
    applyRestructure,
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
    replacePrimaryFile,
    archiveAttachment,
    publish,
    approvePublication,
    withdrawPublication,
    getPublication,
    publicationMarkdownUrl: (_scope, id, publicationId) => `/documents/${id}/publications/${publicationId}/markdown`,
    publicationManifestUrl: (_scope, id, publicationId) => `/documents/${id}/publications/${publicationId}/manifest`,
    publicationArtifactUrl: (_scope, id, publicationId, artifactId) => `/documents/${id}/publications/${publicationId}/artifacts/${artifactId}/download`,
    publicationExportUrl: (_scope, id, publicationId, format) => `/documents/${id}/publications/${publicationId}/export?export_format=${format}`,
    exportUrl: (_scope, id, format = 'md', attachmentIds = []) => {
      const query = new URLSearchParams({ export_format: format })
      attachmentIds.forEach((attachmentId) => query.append('attachment_ids', attachmentId))
      return `/documents/${id}/export?${query.toString()}`
    },
    attachmentDownloadUrl: (_scope, id, attachmentId) => `/documents/${id}/attachments/${attachmentId}/download`,
    archive: vi.fn().mockResolvedValue(undefined),
    addReference,
    listKeyBindings,
    declareKeyBinding,
    archiveKeyBinding,
    listDocumentKeys,
    browseKeyBindings,
  }
  const workspaces: WorkspaceClient = {
    loadMsp: vi.fn(), loadOrganization: vi.fn(),
    searchOrganizations: vi.fn().mockResolvedValue({ results: [{ id: 'org-1', name: 'Acme', classifications: ['client'], capabilities: ['documentation'] }], page: 1, page_size: 15, has_more: false }),
  }
  return { documents, workspaces, getDocument, createDocument, createFileBacked, replacePrimaryFile, updateDocument, previewRestructure, applyRestructure, addReference, addPlacement, updatePlacement, removePlacement, getReuseImpact, updateSharedBlock, detachPlacement, searchMentionEntities, searchBlockLibrary, instantiateTemplate, importMarkdown, uploadAttachment, archiveAttachment, publish, approvePublication, withdrawPublication, getPublication, saveRemoteSource, checkRemoteSource, applyRemoteObservation, publication, listKeyBindings, declareKeyBinding, archiveKeyBinding, listDocumentKeys, browseKeyBindings, keyBinding }
}

it('lists titles and persists an independently edited block', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, updateSharedBlock } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await waitFor(() => expect(screen.getByRole('heading', { name: 'Firewall' })).toBeVisible())
  expect(screen.queryByText('Document blocks')).not.toBeInTheDocument()
  expect(screen.queryByText(/Select a block to edit/)).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Edit this content' }))
  await user.clear(await screen.findByRole('textbox', { name: 'Document Markdown' }))
  await user.type(screen.getByRole('textbox', { name: 'Document Markdown' }), '# Updated')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(updateSharedBlock).toHaveBeenCalledWith({}, 'doc-1', 'placement-1', '# Updated', 'revision-1'))
  expect(screen.getByRole('status')).toHaveTextContent('Content saved.')
})

it('opens an authorized document supplied by a workspace deep link', async () => {
  const { documents, workspaces } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} initialDocumentId="doc-1" />)

  expect(await screen.findByRole('heading', { name: 'Firewall' })).toBeVisible()
})

it('retrieves an authorized deep-linked document that is outside the first list page', async () => {
  const { documents, workspaces, getDocument } = clients()
  documents.list = vi.fn().mockResolvedValue({ results: [], count: 51 })
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} initialDocumentId="doc-1" />)

  expect(await screen.findByRole('heading', { name: 'Firewall' })).toBeVisible()
  expect(getDocument).toHaveBeenCalledWith({}, 'doc-1', expect.any(AbortSignal))
})

it('loads revision history and a selected diff', async () => {
  const user = userEvent.setup()
  const { documents, workspaces } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(screen.getByRole('button', { name: 'History' }))
  await user.click(await screen.findByRole('button', { name: /Revision 1/ }))
  expect(await screen.findByText('+# Firewall')).toBeInTheDocument()
})

it('exports an exact editable snapshot and includes only explicitly selected files in the portable ZIP', async () => {
  const user = userEvent.setup()
  const { documents, workspaces } = clients()
  const attachment = { id: 'attachment-1', filename: 'private-notes.txt', media_type: 'text/plain', size: 24, checksum: 'a'.repeat(64), scan_status: 'clean' as const, scan_engine: 'test-scanner', scanned_at: '2026-08-09T00:00:00Z', created_at: '2026-08-09T00:00:00Z' }
  const primary = { ...attachment, id: 'primary-1', filename: 'approved-guide.txt', version_number: 1, replaces_id: null, is_current: true }
  documents.list = vi.fn().mockResolvedValue({ results: [{ ...document, attachments: [attachment], attachment_count: 1, primary_file: primary, primary_file_versions: [primary] }], count: 1 })
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(screen.getByRole('button', { name: 'Export' }))

  expect(await screen.findByRole('heading', { name: 'Export editable snapshot' })).toBeVisible()
  expect(screen.getByText(/not a retained STATIC publication/)).toBeVisible()
  expect(screen.getByRole('link', { name: 'Markdown' })).toHaveAttribute('href', '/documents/doc-1/export?export_format=md')
  expect(screen.getByRole('link', { name: 'DOCX' })).toHaveAttribute('href', '/documents/doc-1/export?export_format=docx')
  expect(screen.getByRole('link', { name: 'Download portable ZIP' })).toHaveAttribute('href', '/documents/doc-1/export?export_format=bundle')

  await user.click(screen.getByRole('checkbox', { name: /private-notes.txt/ }))
  expect(screen.getByRole('link', { name: 'Download portable ZIP' })).toHaveAttribute(
    'href',
    '/documents/doc-1/export?export_format=bundle&attachment_ids=attachment-1',
  )
  expect(screen.getByRole('checkbox', { name: /approved-guide.txt/ })).not.toBeChecked()
})

it('previews and explicitly restructures legacy content from document settings', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, previewRestructure, applyRestructure } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  expect(screen.queryByText('Separate legacy content')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Document settings' }))
  await user.click(screen.getByRole('button', { name: 'Review section conversion' }))
  expect(await screen.findByRole('heading', { name: 'Separate legacy content' })).toBeVisible()
  expect(screen.getByText(/2 independently editable sections/)).toBeVisible()
  expect(screen.getByText('Require MFA')).toBeVisible()
  expect(previewRestructure).toHaveBeenCalledWith({}, 'doc-1')
  await user.click(screen.getByRole('button', { name: 'Create 2 sections' }))
  await waitFor(() => expect(applyRestructure).toHaveBeenCalledWith({}, 'doc-1', 'revision-1'))
  expect(screen.getByRole('status')).toHaveTextContent('Content separated into 2 editable sections.')
  expect(screen.getByText('Require MFA.')).toBeVisible()
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
  await user.click(screen.getByRole('button', { name: 'History' }))
  expect(await screen.findByText(/page 1/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Older' }))
  expect(await screen.findByText(/page 2/)).toBeInTheDocument()
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
  await user.click(screen.getByRole('button', { name: 'Edit this content' }))
  const editor = await screen.findByRole('textbox', { name: 'Document Markdown' })
  await user.clear(editor); await user.type(editor, '# My unsaved draft')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Newer content detected')
  expect(editor).toHaveValue('# My unsaved draft')
  expect(screen.getByText(/Server edit/)).toBeInTheDocument()
  expect(screen.getByRole('textbox', { name: 'Document Markdown' })).toHaveValue('# My unsaved draft')
})

it('creates a document and adds an MSP-owned reference to a searched client', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, createDocument, addReference } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await screen.findByRole('button', { name: /Firewall standard/ })
  await user.click(screen.getByRole('button', { name: 'New document' }))
  await user.type(screen.getByLabelText('Document title'), 'New guide')
  await user.type(screen.getByRole('textbox', { name: 'Document Markdown' }), 'Portable Markdown')
  await user.click(screen.getByRole('button', { name: 'Create document' }))
  await waitFor(() => expect(createDocument).toHaveBeenCalledWith({}, { title: 'New guide', markdown: 'Portable Markdown', category: 'general', is_template: false, library_visible: false }))
  await user.click(screen.getByRole('button', { name: 'Document settings' }))
  await user.click(screen.getByRole('button', { name: 'Client listings' }))
  await user.type(screen.getByRole('searchbox', { name: 'Find client organization' }), 'Acm')
  await user.click(await screen.findByRole('button', { name: /Acme/ }))
  expect(addReference).toHaveBeenCalledWith('doc-2', 'org-1')
})

it('creates a file-backed document with notes and exposes retained primary-file versions', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, createFileBacked, replacePrimaryFile } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await screen.findByRole('button', { name: /Firewall standard/ })
  await user.click(screen.getByRole('button', { name: 'New document' }))
  await user.click(screen.getByRole('button', { name: 'Upload file' }))
  await user.type(screen.getByLabelText('Document title'), 'Vendor runbook')
  const source = new File(['approved instructions'], 'runbook.txt', { type: 'text/plain' })
  await user.upload(screen.getByLabelText('Primary file'), source)
  await user.type(screen.getByRole('textbox', { name: 'Document Markdown' }), '## Local notes')
  await user.click(screen.getByRole('button', { name: 'Create file-backed document' }))
  await waitFor(() => expect(createFileBacked).toHaveBeenCalledWith({}, { title: 'Vendor runbook', notes: '## Local notes', category: 'general', file: source }))
  expect(screen.getByText('Primary file · version 1 · 512 bytes')).toBeVisible()
  expect(screen.getByRole('link', { name: /Download/ })).toHaveAttribute('href', '/documents/doc-file/attachments/primary-1/download')

  const replacement = new File(['%PDF-1.4 replacement'], 'firewall-v2.pdf', { type: 'application/pdf' })
  await user.upload(screen.getByLabelText('Replacement primary file'), replacement)
  await waitFor(() => expect(replacePrimaryFile).toHaveBeenCalledWith({}, 'doc-file', replacement))
  expect(await screen.findByText('Primary file · version 2 · 512 bytes')).toBeVisible()
})

it('adds a visible document block live and can pin its resolved revision', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, addPlacement, updatePlacement } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(screen.getByRole('button', { name: 'Add content here' }))
  await user.click(screen.getByRole('button', { name: 'Existing content' }))
  await user.selectOptions(screen.getByLabelText('Link a document'), 'doc-source')
  await user.click(screen.getByRole('button', { name: 'Insert document' }))
  await waitFor(() => expect(addPlacement).toHaveBeenCalledWith({}, 'doc-1', { source_document_id: 'doc-source', resolution_mode: 'live', pinned_revision_id: null, position: 1, audience_profile: 'shared' }))
  await user.click(screen.getByRole('button', { name: 'Keep this version' }))
  expect(updatePlacement).toHaveBeenCalledWith({}, 'doc-1', 'placement-reused', { resolution_mode: 'pinned', pinned_revision_id: 'revision-source' })
})

it('shows explicit placement audiences, previews each publication, and updates a profile', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, updatePlacement } = clients()
  const audienceDocument: DocumentRecord = {
    ...document,
    placements: [
      primaryPlacement,
      { ...primaryPlacement, id: 'placement-internal', block_id: 'block-internal', position: 1, is_primary: false, audience_profile: 'msp_internal', resolved_html: '<p>Operator sentinel</p>', resolved_markdown: 'Operator sentinel' },
      { ...primaryPlacement, id: 'placement-client', block_id: 'block-client', position: 2, is_primary: false, audience_profile: 'client_visible', resolved_html: '<p>Client sentinel</p>', resolved_markdown: 'Client sentinel' },
    ],
    placement_count: 3,
  }
  vi.spyOn(documents, 'list').mockResolvedValue({ results: [audienceDocument], count: 1 })
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))

  expect(screen.getByText('MSP and client')).toBeVisible()
  expect(screen.getByText('MSP only')).toBeVisible()
  expect(screen.getByText('Client only')).toBeVisible()
  await user.selectOptions(screen.getByLabelText('Preview'), 'client_visible')
  expect(screen.queryByText('Operator sentinel')).not.toBeInTheDocument()
  expect(screen.getByText('Client sentinel')).toBeVisible()
  expect(screen.getByText('2 visible sections')).toBeVisible()

  await user.selectOptions(screen.getByLabelText('Preview'), 'all')
  const internalSection = screen.getByText('Operator sentinel').closest('li')
  expect(internalSection).not.toBeNull()
  await user.click(within(internalSection!).getByRole('button', { name: 'Include for client only' }))
  expect(updatePlacement).toHaveBeenCalledWith({}, 'doc-1', 'placement-internal', { audience_profile: 'client_visible' })
})

it('creates a typed local block at an explicit document position', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, addPlacement } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(screen.getByRole('button', { name: 'Add content here' }))
  await user.click(screen.getByRole('button', { name: 'Heading' }))
  await user.clear(screen.getByRole('textbox', { name: 'Document Markdown' }))
  await user.type(screen.getByRole('textbox', { name: 'Document Markdown' }), '## Addressing')
  await user.click(screen.getByRole('button', { name: 'Add' }))
  await waitFor(() => expect(addPlacement).toHaveBeenCalledWith({}, 'doc-1', {
    operation: 'create_block',
    block_kind: 'heading',
    block_name: 'Heading',
    markdown: '## Addressing',
    position: 1,
    library_visible: false,
    audience_profile: 'shared',
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
  await user.click(screen.getByRole('button', { name: 'Add content here' }))
  await user.click(screen.getByRole('button', { name: 'Existing content' }))
  expect(await screen.findByText('Printer isolation rationale')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Insert' }))
  await waitFor(() => expect(addPlacement).toHaveBeenCalledWith({ organizationId: 'org-1' }, 'doc-1', {
    operation: 'reuse_block', source_block_id: 'block-shared', resolution_mode: 'live', pinned_revision_id: null, position: 1, audience_profile: 'shared',
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
  await user.click(screen.getByRole('button', { name: 'Document settings' }))
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
  await user.click(screen.getByRole('button', { name: 'Document settings' }))
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
  expect(screen.getByRole('status')).toHaveTextContent('Reviewed source change applied as a new revision.')
})

it('reviews shared audiences and detaches a reused block', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, addPlacement, getReuseImpact, detachPlacement } = clients()
  const reusedImpact = { block_id: 'block-source', block_name: 'Shared checklist — content', revision_id: 'revision-source', revision_number: 1, checksum: 'abc123', markdown: 'Shared content', audiences: [{ relationship: 'placement' as const, document_id: 'doc-1', document_title: 'Firewall standard', workspace_kind: 'msp' as const, workspace_id: 'tenant', workspace_name: 'TekDocs MSP', resolution_mode: 'live' as const, will_update: true }], live_audience_count: 1, pinned_audience_count: 0, can_edit_shared: false, can_detach: true, requires_mfa: true, truncated: false }
  getReuseImpact.mockResolvedValue(reusedImpact)
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(screen.getByRole('button', { name: 'Add content here' }))
  await user.click(screen.getByRole('button', { name: 'Existing content' }))
  await user.selectOptions(screen.getByLabelText('Link a document'), 'doc-source')
  await user.click(screen.getByRole('button', { name: 'Insert document' }))
  await waitFor(() => expect(addPlacement).toHaveBeenCalled())
  await user.click(screen.getAllByRole('button', { name: 'Reuse and impact' })[1])
  expect(await screen.findByRole('heading', { name: 'Where this content is used' })).toBeVisible()
  expect(screen.getByText('Will update')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Make an independent copy here' }))
  expect(detachPlacement).toHaveBeenCalledWith({}, 'doc-1', 'placement-reused')
})

it('imports Markdown and manages a private attachment link', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, importMarkdown, uploadAttachment, archiveAttachment } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await screen.findByRole('button', { name: /Firewall standard/ })
  await user.upload(screen.getByLabelText('Markdown file to import'), new File(['# Imported'], 'imported.md', { type: 'text/markdown' }))
  await waitFor(() => expect(importMarkdown).toHaveBeenCalledWith({}, expect.any(File), 'imported', 'general', false))
  await user.click(screen.getByRole('button', { name: 'Add content here' }))
  await user.click(screen.getByRole('button', { name: 'File' }))
  await user.upload(screen.getByLabelText('Attachment file'), new File(['notes'], 'notes.txt', { type: 'text/plain' }))
  await waitFor(() => expect(uploadAttachment).toHaveBeenCalledWith({}, 'doc-imported', expect.any(File)))
  await user.click(await screen.findByRole('button', { name: 'Insert here' }))
  expect(screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Document Markdown' }).value).toContain('tekdocs://attachment/attachment-1')
  await user.click(screen.getByRole('button', { name: /Files \(1\)/ }))
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
  await user.click(screen.getByRole('button', { name: /Files/ }))
  expect(screen.getByRole('button', { name: 'View PDF' })).toBeVisible()
  expect(screen.getAllByRole('button', { name: 'Insert here' })).toHaveLength(2)
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
  expect(screen.getByRole('link', { name: 'Download PDF' })).toHaveAttribute('href', '/documents/doc-1/publications/publication-1/export?export_format=pdf')
  expect(screen.getByText(`SHA-256 ${'a'.repeat(64)}`)).toBeVisible()
  expect(screen.getByRole('link', { name: 'Download Markdown' })).toHaveAttribute('href', '/documents/doc-1/publications/publication-1/export?export_format=md')
  expect(screen.getByRole('link', { name: 'Download DOCX' })).toHaveAttribute('href', '/documents/doc-1/publications/publication-1/export?export_format=docx')
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

it('declares a key binding, inserts a key, and reports what has not resolved', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, declareKeyBinding, archiveKeyBinding, searchMentionEntities } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))

  // The unresolved count is on the control itself, so an author sees there is
  // something to fix without opening the panel.
  await user.click(await screen.findByRole('button', { name: /^Keys/ }))
  expect(await screen.findByRole('button', { name: 'Keys (1)' })).toBeInTheDocument()

  await user.type(screen.getByLabelText('Declare'), 'subject')
  await user.type(screen.getByRole('searchbox', { name: /TekDocs record/ }), 'Edge')
  await waitFor(() => expect(searchMentionEntities).toHaveBeenCalled())
  await user.click(await screen.findByRole('button', { name: /Router A/ }))
  await waitFor(() => expect(declareKeyBinding).toHaveBeenCalledWith({}, 'doc-1', 'subject', 'entity-1'))

  // The report names the key and why it did not resolve, rather than leaving a blank.
  expect(screen.getByText('subject.serial_number')).toBeInTheDocument()
  expect(screen.getByText(/Serial number · empty/)).toBeInTheDocument()

  // Inserting writes the same autolink shape the dialect already understands, into
  // whichever editor is open.
  await user.click(screen.getByRole('button', { name: 'Edit this content' }))
  await user.selectOptions(screen.getByLabelText('subject'), 'serial_number')
  expect(screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Document Markdown' }).value)
    .toContain('<tekdocs://key/subject.serial_number>')

  await user.click(screen.getByRole('button', { name: 'Retire subject' }))
  expect(archiveKeyBinding).toHaveBeenCalledWith({}, 'doc-1', 'binding-1')
})

it('inserts a content key on its own Markdown line', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, listKeyBindings, keyBinding } = clients()
  listKeyBindings.mockResolvedValue({
    results: [{ ...keyBinding, name: 'procedure', target_entity_type: 'document_block', addressable_fields: ['content'] }],
    count: 1,
    addressable_entity_types: ['client_asset', 'document_block', 'network_device'],
  })
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(await screen.findByRole('button', { name: /^Keys/ }))
  await user.click(screen.getByRole('button', { name: 'Edit this content' }))

  await user.selectOptions(screen.getByLabelText('procedure'), 'content')

  expect(screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Document Markdown' }).value)
    .toBe('# Firewall\n\n<tekdocs://key/procedure.content>\n')
})

it('answers a binding name the server would refuse before the request is made', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, declareKeyBinding, searchMentionEntities } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(await screen.findByRole('button', { name: /^Keys/ }))

  // A capitalised word is the natural first guess and the grammar forbids it. Taking
  // the capital out as it is typed keeps the field always in a state the server accepts.
  await user.type(screen.getByLabelText('Declare'), 'Network')
  expect(screen.getByLabelText<HTMLInputElement>('Declare').value).toBe('network')

  await user.clear(screen.getByLabelText('Declare'))
  await user.type(screen.getByLabelText('Declare'), '9 gateway')
  expect(screen.getByLabelText('Declare')).toHaveAttribute('aria-invalid', 'true')
  expect(screen.getByRole('alert')).toHaveTextContent('Use lowercase letters, digits and underscores')

  await user.type(screen.getByRole('searchbox', { name: /TekDocs record/ }), 'Edge')
  await waitFor(() => expect(searchMentionEntities).toHaveBeenCalled())
  expect(await screen.findByRole('button', { name: /Router A/ })).toBeDisabled()
  expect(declareKeyBinding).not.toHaveBeenCalled()
})

it('does not offer a record no key could read', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, searchMentionEntities } = clients()
  searchMentionEntities.mockResolvedValue({
    results: [{ id: 'entity-9', display_name: 'Onboarding guide', entity_type: 'document', workspace_label: 'Acme Dental' }],
    page: 1, page_size: 20, count: 1, has_more: false,
  })
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(await screen.findByRole('button', { name: /^Keys/ }))
  await user.type(screen.getByLabelText('Declare'), 'guide')
  await user.type(screen.getByRole('searchbox', { name: /TekDocs record/ }), 'Onboarding')

  // The server names the record kinds a binding may target; the picker says so in place
  // rather than letting the author discover it from a rejected request.
  const option = await screen.findByRole('button', { name: /Onboarding guide/ })
  expect(option).toBeDisabled()
  expect(option).toHaveTextContent('Keys cannot read fields from this kind of record yet')
})

it('shows the blast radius of a bound record and finds bindings across the workspace', async () => {
  const user = userEvent.setup()
  const { documents, workspaces, browseKeyBindings } = clients()
  render(<Documentation workspace={null} client={documents} workspaceClient={workspaces} />)
  await user.click(await screen.findByRole('button', { name: /Firewall standard/ }))
  await user.click(await screen.findByRole('button', { name: /^Keys/ }))

  // Where-used: the other document that quotes this record is named while binding,
  // not discovered after an edit has already changed it.
  expect(await screen.findByText(/Also used by: Escalation guide/)).toBeInTheDocument()

  await user.type(screen.getByRole('searchbox', { name: /Find bindings/ }), 'Edge')
  await waitFor(() => expect(browseKeyBindings).toHaveBeenCalledWith({}, 'Edge', expect.anything()))
  const browser = within(await screen.findByRole('list', { name: 'Bindings across this workspace' }))
  expect(browser.getByText('Edge firewall')).toBeInTheDocument()
})
