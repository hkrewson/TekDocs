import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { vi } from 'vitest'
import { NavigationGuardProvider } from '../navigation/NavigationGuardProvider'
import { RepositoryContentPanel } from './RepositoryContentPanel'
import { RepositoryConflictError, type RepositoryClient, type RepositorySource } from './repositoryApi'

const commit = 'a'.repeat(40)
const blob = 'b'.repeat(40)
const initial: RepositorySource = {
  content_id: 'content-1', path: 'docs/guide.md', kind: 'document', title: 'Guide',
  markdown: 'First revision.\n', source: '---\ntitle: Guide\n---\nFirst revision.\n',
  source_blob: blob, accepted_commit: commit, indexed_commit: commit,
}

function setup(overrides: Partial<RepositoryClient> = {}, organizationId?: string) {
  const save = vi.fn().mockResolvedValue({ ...initial, markdown: 'Changed revision.\n', accepted_commit: 'c'.repeat(40), indexed_commit: 'c'.repeat(40) })
  const client = {
    list: vi.fn().mockResolvedValue({ results: [{ id: 'content-1', title: 'Guide', kind: 'document', path: 'docs/guide.md' }], accepted_commit: commit, indexed_commit: commit, count: 1, has_more: false }),
    source: vi.fn().mockResolvedValue(initial),
    exportSources: vi.fn().mockResolvedValue({ content: new Blob(['snapshot']), name: 'tekdocs-repository-aaaaaaaaaaaa.zip' }),
    exportEditableBundle: vi.fn().mockResolvedValue({ content: new Blob(['bundle']), name: 'tekdocs-repository-editable-aaaaaaaaaaaa.zip' }),
    exportHtml: vi.fn().mockResolvedValue({ content: new Blob(['<html>Saved</html>'], { type: 'text/html' }), name: 'repository-document.html', commit }),
    exportPdf: vi.fn().mockResolvedValue({ content: new Blob(['%PDF-saved'], { type: 'application/pdf' }), name: 'repository-document.pdf', commit }),
    exportDocx: vi.fn().mockResolvedValue({ content: new Blob(['PK\x03\x04saved']), name: 'repository-document.docx', commit }),
    uploadAttachment: vi.fn().mockResolvedValue({ id: '11111111-1111-4111-8111-111111111111', filename: 'setup [staff].txt', size: 5, scan_status: 'clean' }),
    listEvidence: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 25, count: 0, has_more: false }),
    staticPublication: vi.fn().mockResolvedValue(null),
    reviewPdf: vi.fn().mockResolvedValue({ content: new Blob(['%PDF-review']), name: 'repository-evidence-snapshot.pdf' }),
    exportStatic: vi.fn().mockResolvedValue({ content: new Blob(['retained']), name: 'repository-static-publication.pdf' }),
    save,
    ...overrides,
  }
  const onClose = vi.fn()
  const router = createMemoryRouter([{
    path: '*', element: <NavigationGuardProvider><RepositoryContentPanel client={client} organizationId={organizationId} onClose={onClose} /></NavigationGuardProvider>,
  }])
  render(<RouterProvider router={router} />)
  return { client, onClose, save }
}

it('uploads to a saved indexed document and leaves its private-file link as an unsaved Markdown draft', async () => {
  const user = userEvent.setup()
  const { client, save } = setup({}, 'org-1')
  await user.click(await screen.findByRole('button', { name: /Guide/ }))
  const file = new File(['steps'], 'setup [staff].txt', { type: 'text/plain' })
  await user.upload(screen.getByLabelText('Attach file to saved document'), file)
  await waitFor(() => expect(client.uploadAttachment).toHaveBeenCalledWith('content-1', file, 'org-1'))
  const linked = 'First revision.\n[setup \\[staff\\].txt](tekdocs://attachment/11111111-1111-4111-8111-111111111111)\n'
  expect(await screen.findByRole('status')).toHaveTextContent('Save to Git to keep its link')
  expect(screen.getByLabelText('Markdown body')).toHaveValue(linked)
  expect(save).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Back to documentation' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(screen.getByLabelText('Markdown body')).toHaveValue(linked)
  await user.click(screen.getByRole('button', { name: 'Save to Git' }))
  await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({
    content_id: 'content-1', base_commit: commit, base_blob: blob, markdown: linked,
  }), 'org-1'))
})

it('preserves a dirty draft and supports retry when attachment upload is denied', async () => {
  const user = userEvent.setup()
  const uploadAttachment = vi.fn()
    .mockRejectedValueOnce(new Error('Upload denied'))
    .mockResolvedValue({ id: '11111111-1111-4111-8111-111111111111', filename: 'steps.txt', size: 5, scan_status: 'clean' })
  setup({ uploadAttachment })
  await user.click(await screen.findByRole('button', { name: /Guide/ }))
  const body = screen.getByLabelText('Markdown body')
  await user.type(body, ' Unsaved')
  const file = new File(['steps'], 'steps.txt', { type: 'text/plain' })
  await user.upload(screen.getByLabelText('Attach file to saved document'), file)
  expect(await screen.findByRole('alert')).toHaveTextContent('Upload denied')
  expect(body).toHaveValue('First revision.\n Unsaved')
  await user.upload(screen.getByLabelText('Attach file to saved document'), file)
  await waitFor(() => expect(uploadAttachment).toHaveBeenCalledTimes(2))
  expect(await screen.findByRole('status')).toHaveTextContent('Save to Git to keep its link')
  expect(body).toHaveValue('First revision.\n Unsaved\n\n[steps.txt](tekdocs://attachment/11111111-1111-4111-8111-111111111111)\n')
})

it('does not offer attachment upload for fragments or unsaved documents', async () => {
  const user = userEvent.setup()
  const fragment = { ...initial, kind: 'fragment' as const }
  const client = setup({ source: vi.fn().mockResolvedValue(fragment) }).client
  await user.click(await screen.findByRole('button', { name: /Guide/ }))
  expect(screen.queryByLabelText('Attach file to saved document')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'New Markdown file' }))
  expect(screen.queryByLabelText('Attach file to saved document')).not.toBeInTheDocument()
  expect(client.uploadAttachment).not.toHaveBeenCalled()
})

it('disables attachment upload while indexing is behind the accepted revision', async () => {
  const user = userEvent.setup()
  const client = setup({ source: vi.fn().mockResolvedValue({ ...initial, indexed_commit: null }) }).client
  await user.click(await screen.findByRole('button', { name: /Guide/ }))
  expect(screen.getByLabelText('Attach file to saved document')).toBeDisabled()
  expect(client.uploadAttachment).not.toHaveBeenCalled()
})

it('preserves a dirty draft through navigation and sends exact base identities on save', async () => {
  const user = userEvent.setup()
  const { save, onClose } = setup()
  expect(screen.getByRole('heading', { name: 'Repository content' })).toHaveFocus()
  await user.click(await screen.findByRole('button', { name: /Guide/ }))
  const body = await screen.findByLabelText('Markdown body')
  await user.clear(body)
  await user.type(body, 'Changed revision.')
  await user.click(screen.getByRole('button', { name: 'Back to documentation' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(onClose).not.toHaveBeenCalled()
  expect(body).toHaveValue('Changed revision.')
  await user.click(screen.getByRole('button', { name: 'Save to Git' }))
  await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({
    operation: 'update', content_id: 'content-1', base_commit: commit, base_blob: blob,
    markdown: 'Changed revision.', title: undefined,
  }), undefined))
  expect(await screen.findByText('Saved as one accepted Git commit.')).toBeInTheDocument()
})

it('loads document-scoped publication history and distinguishes signed evidence from a verified STATIC record', async () => {
  const user = userEvent.setup()
  const evidence = { id: 'evidence-1', content_id: 'content-1', title: 'Evidence A', audience: 'msp_internal', source_commit: commit, signed_at: '2026-10-09T12:00:00Z' }
  const second = { ...evidence, id: 'evidence-2', title: 'Evidence B', audience: 'client_visible' }
  const listEvidence = vi.fn()
    .mockResolvedValueOnce({ results: [evidence], page: 1, page_size: 25, count: 2, has_more: true })
    .mockResolvedValue({ results: [second], page: 2, page_size: 25, count: 2, has_more: false })
  const staticPublication = vi.fn().mockResolvedValue({ id: 'static-1', source_commit: commit, content_digest: 'd'.repeat(64), verified: true, permits_distribution: false })
  setup({ listEvidence, staticPublication })
  expect(screen.queryByRole('button', { name: 'Load publication history' })).not.toBeInTheDocument()
  await user.click(await screen.findByRole('button', { name: /Guide/ }))
  await user.type(screen.getByLabelText('Markdown body'), ' Unsaved')
  expect(listEvidence).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Load publication history' }))
  expect(await screen.findByRole('button', { name: /Evidence A/ })).toBeInTheDocument()
  expect(screen.getByText(/MSP internal/)).toBeInTheDocument()
  expect(listEvidence).toHaveBeenCalledWith('content-1', undefined, 1, expect.any(AbortSignal))
  await user.click(screen.getByRole('button', { name: 'Load more evidence' }))
  expect(await screen.findByRole('button', { name: /Evidence B/ })).toBeInTheDocument()
  expect(listEvidence).toHaveBeenCalledWith('content-1', undefined, 2, expect.any(AbortSignal))
  await user.click(screen.getByRole('button', { name: /Evidence A/ }))
  expect(await screen.findByText(/passed integrity verification/)).toBeInTheDocument()
  expect(staticPublication).toHaveBeenCalledWith('evidence-1', undefined, expect.any(AbortSignal))
  expect(screen.getByLabelText('Markdown body')).toHaveValue('First revision.\n Unsaved')
})

it('keeps publication history denial retryable and does not claim unfinalized evidence is published', async () => {
  const user = userEvent.setup()
  const evidence = { id: 'evidence-1', content_id: 'content-1', title: 'Evidence A', audience: 'msp_internal', source_commit: commit, signed_at: '2026-10-09T12:00:00Z' }
  const listEvidence = vi.fn().mockRejectedValueOnce(new Error('Denied')).mockResolvedValue({ results: [evidence], page: 1, page_size: 25, count: 1, has_more: false })
  const staticPublication = vi.fn().mockResolvedValue(null)
  setup({ listEvidence, staticPublication })
  await user.click(await screen.findByRole('button', { name: /Guide/ }))
  await user.click(screen.getByRole('button', { name: 'Load publication history' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Publication history is unavailable')
  await user.click(screen.getByRole('button', { name: 'Retry' }))
  await user.click(await screen.findByRole('button', { name: /Evidence A/ }))
  expect(await screen.findByText(/No finalized STATIC record exists/)).toBeInTheDocument()
  expect(listEvidence).toHaveBeenCalledTimes(2)
})

it('keeps review-PDF denial retryable without turning signed evidence into a publication', async () => {
  const user = userEvent.setup()
  const evidence = { id: 'evidence-1', content_id: 'content-1', title: 'Evidence A', audience: 'msp_internal', source_commit: commit, signed_at: '2026-10-09T12:00:00Z' }
  const reviewPdf = vi.fn()
    .mockRejectedValueOnce(new Error('Denied'))
    .mockResolvedValue({ content: new Blob(['%PDF-review'], { type: 'application/pdf' }), name: 'repository-evidence-snapshot.pdf' })
  const createObjectURL = vi.fn().mockReturnValue('blob:review-pdf')
  const revokeObjectURL = vi.fn()
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.download).toBe('repository-evidence-snapshot.pdf')
  })
  const originalCreate = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
  const originalRevoke = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL')
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
  try {
    setup({
      listEvidence: vi.fn().mockResolvedValue({ results: [evidence], page: 1, page_size: 25, count: 1, has_more: false }),
      staticPublication: vi.fn().mockResolvedValue(null),
      reviewPdf,
    })
    await user.click(await screen.findByRole('button', { name: /Guide/ }))
    await user.type(screen.getByLabelText('Markdown body'), ' Unsaved')
    await user.click(screen.getByRole('button', { name: 'Load publication history' }))
    await user.click(await screen.findByRole('button', { name: /Evidence A/ }))
    expect(await screen.findByText(/No finalized STATIC record exists/)).toBeInTheDocument()
    expect(screen.getByText(/not a finalized STATIC publication or client download/)).toBeInTheDocument()
    const download = screen.getByRole('button', { name: 'Download review PDF' })
    await user.click(download)
    expect(await screen.findByRole('alert')).toHaveTextContent('review PDF could not be downloaded')
    expect(click).not.toHaveBeenCalled()
    await user.click(download)
    await waitFor(() => expect(click).toHaveBeenCalledOnce())
    expect(reviewPdf).toHaveBeenCalledWith('evidence-1', undefined, expect.any(AbortSignal))
    expect(screen.getByLabelText('Markdown body')).toHaveValue('First revision.\n Unsaved')
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:review-pdf'))
  } finally {
    if (originalCreate) Object.defineProperty(URL, 'createObjectURL', originalCreate)
    else Reflect.deleteProperty(URL, 'createObjectURL')
    if (originalRevoke) Object.defineProperty(URL, 'revokeObjectURL', originalRevoke)
    else Reflect.deleteProperty(URL, 'revokeObjectURL')
    click.mockRestore()
  }
})

it('keeps a denied STATIC check retryable and flags an unverified finalized record', async () => {
  const user = userEvent.setup()
  const evidence = { id: 'evidence-1', content_id: 'content-1', title: 'Evidence A', audience: 'msp_internal', source_commit: commit, signed_at: '2026-10-09T12:00:00Z' }
  const staticPublication = vi.fn()
    .mockRejectedValueOnce(new Error('Denied'))
    .mockResolvedValue({ id: 'static-1', source_commit: commit, content_digest: 'd'.repeat(64), verified: false, permits_distribution: false })
  setup({
    listEvidence: vi.fn().mockResolvedValue({ results: [evidence], page: 1, page_size: 25, count: 1, has_more: false }),
    staticPublication,
  })
  await user.click(await screen.findByRole('button', { name: /Guide/ }))
  await user.click(screen.getByRole('button', { name: 'Load publication history' }))
  await user.click(await screen.findByRole('button', { name: /Evidence A/ }))
  expect(await screen.findByRole('alert')).toHaveTextContent('STATIC record could not be checked')
  await user.click(screen.getByRole('button', { name: 'Retry' }))
  expect(await screen.findByText(/failed integrity verification/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Download retained PDF' })).not.toBeInTheDocument()
  expect(staticPublication).toHaveBeenCalledTimes(2)
})

it('downloads a verified retained file after approval and keeps denial retryable with a dirty draft', async () => {
  const user = userEvent.setup()
  const evidence = { id: 'evidence-1', content_id: 'content-1', title: 'Evidence A', audience: 'msp_internal', source_commit: commit, signed_at: '2026-10-09T12:00:00Z' }
  const exportStatic = vi.fn()
    .mockRejectedValueOnce(new Error('Denied'))
    .mockResolvedValue({ content: new Blob(['%PDF-retained'], { type: 'application/pdf' }), name: 'repository-static-publication.pdf' })
  const createObjectURL = vi.fn().mockReturnValue('blob:retained-pdf')
  const revokeObjectURL = vi.fn()
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.download).toBe('repository-static-publication.pdf')
    expect(this.href).toBe('blob:retained-pdf')
  })
  const originalCreate = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
  const originalRevoke = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL')
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
  try {
    setup({
      listEvidence: vi.fn().mockResolvedValue({ results: [evidence], page: 1, page_size: 25, count: 1, has_more: false }),
      staticPublication: vi.fn().mockResolvedValue({ id: 'static-1', source_commit: commit, content_digest: 'd'.repeat(64), verified: true, permits_distribution: false }),
      exportStatic,
    }, 'org-1')
    await user.click(await screen.findByRole('button', { name: /Guide/ }))
    await user.type(screen.getByLabelText('Markdown body'), ' Unsaved')
    expect(screen.queryByRole('button', { name: 'Download retained PDF' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Load publication history' }))
    await user.click(await screen.findByRole('button', { name: /Evidence A/ }))
    const download = await screen.findByRole('button', { name: 'Download retained PDF' })
    expect(screen.getByRole('button', { name: 'Download retained Markdown' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Download retained HTML' })).toBeInTheDocument()
    await user.click(download)
    expect(await screen.findByRole('alert')).toHaveTextContent('retained file could not be downloaded')
    expect(click).not.toHaveBeenCalled()
    await user.click(download)
    await waitFor(() => expect(click).toHaveBeenCalledOnce())
    expect(exportStatic).toHaveBeenCalledWith('evidence-1', 'pdf', 'd'.repeat(64), 'org-1', expect.any(AbortSignal))
    expect(screen.getByLabelText('Markdown body')).toHaveValue('First revision.\n Unsaved')
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:retained-pdf'))
  } finally {
    if (originalCreate) Object.defineProperty(URL, 'createObjectURL', originalCreate)
    else Reflect.deleteProperty(URL, 'createObjectURL')
    if (originalRevoke) Object.defineProperty(URL, 'revokeObjectURL', originalRevoke)
    else Reflect.deleteProperty(URL, 'revokeObjectURL')
    click.mockRestore()
  }
})

it('downloads only saved indexed HTML while keeping a dirty draft', async () => {
  const user = userEvent.setup()
  const exportHtml = vi.fn().mockResolvedValue({ content: new Blob(['<html>Saved</html>'], { type: 'text/html' }), name: 'repository-document.html', commit })
  const createObjectURL = vi.fn().mockReturnValue('blob:saved-html')
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.download).toBe('repository-document.html')
    expect(this.href).toBe('blob:saved-html')
  })
  const originalCreate = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
  try {
    setup({ exportHtml })
    expect(screen.queryByRole('button', { name: 'Download saved HTML' })).not.toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: /Guide/ }))
    await user.type(screen.getByLabelText('Markdown body'), ' Unsaved')
    expect(screen.getByText(/^HTML uses the saved, indexed Git revision/)).toHaveTextContent('live entity and field values')
    await user.click(screen.getByRole('button', { name: 'Download saved HTML' }))
    await waitFor(() => expect(click).toHaveBeenCalledOnce())
    expect(exportHtml).toHaveBeenCalledWith('content-1', undefined)
    const exported = createObjectURL.mock.calls[0][0] as Blob
    expect(exported.type).toBe('text/html')
    const reader = new FileReader()
    const loaded = new Promise<string>((resolve) => { reader.onload = () => resolve(reader.result as string) })
    reader.readAsText(exported)
    expect(await loaded).toBe('<html>Saved</html>')
    expect(screen.getByLabelText('Markdown body')).toHaveValue('First revision.\n Unsaved')
  } finally {
    if (originalCreate) Object.defineProperty(URL, 'createObjectURL', originalCreate)
    else Reflect.deleteProperty(URL, 'createObjectURL')
    click.mockRestore()
  }
})

it('keeps a denied HTML download retryable and refuses a changed revision', async () => {
  const user = userEvent.setup()
  const exportHtml = vi.fn()
    .mockRejectedValueOnce(new Error('Denied'))
    .mockResolvedValueOnce({ content: new Blob(['stale']), name: 'repository-document.html', commit: 'c'.repeat(40) })
    .mockResolvedValue({ content: new Blob(['current']), name: 'repository-document.html', commit })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const originalCreate = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn().mockReturnValue('blob:html') })
  try {
    setup({ exportHtml })
    await user.click(await screen.findByRole('button', { name: /Guide/ }))
    const download = screen.getByRole('button', { name: 'Download saved HTML' })
    await user.click(download)
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be downloaded')
    expect(click).not.toHaveBeenCalled()
    await user.click(download)
    expect(await screen.findByRole('alert')).toHaveTextContent('revision changed')
    expect(click).not.toHaveBeenCalled()
    await user.click(download)
    await waitFor(() => expect(click).toHaveBeenCalledOnce())
    expect(exportHtml).toHaveBeenCalledTimes(3)
  } finally {
    if (originalCreate) Object.defineProperty(URL, 'createObjectURL', originalCreate)
    else Reflect.deleteProperty(URL, 'createObjectURL')
    click.mockRestore()
  }
})

it('offers live PDF only for an indexed document and keeps denial and stale revisions download-free', async () => {
  const user = userEvent.setup()
  const exportPdf = vi.fn()
    .mockRejectedValueOnce(new Error('Denied'))
    .mockResolvedValueOnce({ content: new Blob(['%PDF-stale']), name: 'repository-document.pdf', commit: 'c'.repeat(40) })
    .mockResolvedValue({ content: new Blob(['%PDF-current'], { type: 'application/pdf' }), name: 'repository-document.pdf', commit })
  const createObjectURL = vi.fn().mockReturnValue('blob:saved-pdf')
  const revokeObjectURL = vi.fn()
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.download).toBe('repository-document.pdf')
    expect(this.href).toBe('blob:saved-pdf')
  })
  const originalCreate = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
  const originalRevoke = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL')
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
  try {
    setup({ exportPdf })
    expect(screen.queryByRole('button', { name: 'Download saved PDF' })).not.toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: /Guide/ }))
    await user.type(screen.getByLabelText('Markdown body'), ' Unsaved')
    expect(screen.getByText(/PDF uses the saved, indexed Git revision/)).toBeInTheDocument()
    const download = screen.getByRole('button', { name: 'Download saved PDF' })
    await user.click(download)
    expect(await screen.findByRole('alert')).toHaveTextContent('saved PDF could not be downloaded')
    expect(click).not.toHaveBeenCalled()
    await user.click(download)
    expect(await screen.findByRole('alert')).toHaveTextContent('revision changed while preparing PDF')
    expect(click).not.toHaveBeenCalled()
    await user.click(download)
    await waitFor(() => expect(click).toHaveBeenCalledOnce())
    expect(exportPdf).toHaveBeenCalledWith('content-1', undefined)
    expect(screen.getByLabelText('Markdown body')).toHaveValue('First revision.\n Unsaved')
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:saved-pdf'))
  } finally {
    if (originalCreate) Object.defineProperty(URL, 'createObjectURL', originalCreate)
    else Reflect.deleteProperty(URL, 'createObjectURL')
    if (originalRevoke) Object.defineProperty(URL, 'revokeObjectURL', originalRevoke)
    else Reflect.deleteProperty(URL, 'revokeObjectURL')
    click.mockRestore()
  }
})

it('offers live DOCX only for an indexed document and preserves an unsaved draft on denial or revision change', async () => {
  const user = userEvent.setup()
  const exportDocx = vi.fn()
    .mockRejectedValueOnce(new Error('Denied'))
    .mockResolvedValueOnce({ content: new Blob(['PK\x03\x04stale']), name: 'repository-document.docx', commit: 'c'.repeat(40) })
    .mockResolvedValue({ content: new Blob(['PK\x03\x04current']), name: 'repository-document.docx', commit })
  const createObjectURL = vi.fn().mockReturnValue('blob:saved-docx')
  const revokeObjectURL = vi.fn()
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.download).toBe('repository-document.docx')
    expect(this.href).toBe('blob:saved-docx')
  })
  const originalCreate = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
  const originalRevoke = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL')
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
  try {
    setup({ exportDocx })
    expect(screen.queryByRole('button', { name: 'Download saved DOCX' })).not.toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: /Guide/ }))
    await user.type(screen.getByLabelText('Markdown body'), ' Unsaved')
    expect(screen.getByText(/DOCX uses the saved, indexed Git revision/)).toBeInTheDocument()
    const download = screen.getByRole('button', { name: 'Download saved DOCX' })
    await user.click(download)
    expect(await screen.findByRole('alert')).toHaveTextContent('saved DOCX could not be downloaded')
    expect(click).not.toHaveBeenCalled()
    await user.click(download)
    expect(await screen.findByRole('alert')).toHaveTextContent('revision changed while preparing DOCX')
    expect(click).not.toHaveBeenCalled()
    await user.click(download)
    await waitFor(() => expect(click).toHaveBeenCalledOnce())
    expect(exportDocx).toHaveBeenCalledWith('content-1', undefined)
    expect(screen.getByLabelText('Markdown body')).toHaveValue('First revision.\n Unsaved')
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:saved-docx'))
  } finally {
    if (originalCreate) Object.defineProperty(URL, 'createObjectURL', originalCreate)
    else Reflect.deleteProperty(URL, 'createObjectURL')
    if (originalRevoke) Object.defineProperty(URL, 'revokeObjectURL', originalRevoke)
    else Reflect.deleteProperty(URL, 'revokeObjectURL')
    click.mockRestore()
  }
})

it('does not offer live exports for a fragment or a document awaiting indexing', async () => {
  const user = userEvent.setup()
  const source = vi.fn().mockResolvedValueOnce({ ...initial, kind: 'fragment' }).mockResolvedValue({ ...initial, indexed_commit: 'c'.repeat(40) })
  setup({ source })
  await user.click(await screen.findByRole('button', { name: /Guide/ }))
  expect(screen.queryByRole('button', { name: 'Download saved HTML' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Download saved PDF' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Download saved DOCX' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /Guide/ }))
  await waitFor(() => expect(source).toHaveBeenCalledTimes(2))
  expect(screen.queryByRole('button', { name: 'Download saved HTML' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Download saved PDF' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Download saved DOCX' })).not.toBeInTheDocument()
})

it('downloads a current Workspace snapshot and keeps a failed attempt recoverable', async () => {
  const user = userEvent.setup()
  const exportSources = vi.fn().mockRejectedValueOnce(new Error('Denied')).mockResolvedValue({
    content: new Blob(['snapshot']), name: 'tekdocs-repository-aaaaaaaaaaaa.zip',
  })
  const createObjectURL = vi.fn().mockReturnValue('blob:snapshot')
  const revokeObjectURL = vi.fn()
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.download).toBe('tekdocs-repository-aaaaaaaaaaaa.zip')
  })
  const originalCreate = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
  const originalRevoke = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL')
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
  try {
    setup({ exportSources })
    const download = await screen.findByRole('button', { name: 'Download Markdown source snapshot' })
    await waitFor(() => expect(download).toBeEnabled())
    expect(screen.getAllByText(/not a backup/)).toHaveLength(2)
    await user.click(download)
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be downloaded')
    expect(click).not.toHaveBeenCalled()
    await user.click(download)
    await waitFor(() => expect(click).toHaveBeenCalledOnce())
    expect(exportSources).toHaveBeenCalledTimes(2)
    expect(exportSources).toHaveBeenCalledWith(undefined)
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:snapshot'))
  } finally {
    if (originalCreate) Object.defineProperty(URL, 'createObjectURL', originalCreate)
    else Reflect.deleteProperty(URL, 'createObjectURL')
    if (originalRevoke) Object.defineProperty(URL, 'revokeObjectURL', originalRevoke)
    else Reflect.deleteProperty(URL, 'revokeObjectURL')
    click.mockRestore()
  }
})

it('keeps an editable-bundle denial retryable without discarding a draft', async () => {
  const user = userEvent.setup()
  const exportEditableBundle = vi.fn().mockRejectedValueOnce(new Error('Missing file')).mockResolvedValue({
    content: new Blob(['bundle']), name: 'tekdocs-repository-editable-aaaaaaaaaaaa.zip',
  })
  const createObjectURL = vi.fn().mockReturnValue('blob:bundle')
  const revokeObjectURL = vi.fn()
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.download).toBe('tekdocs-repository-editable-aaaaaaaaaaaa.zip')
  })
  const originalCreate = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
  const originalRevoke = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL')
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
  try {
    setup({ exportEditableBundle })
    await user.click(await screen.findByRole('button', { name: /Guide/ }))
    const editor = await screen.findByLabelText('Markdown body')
    await user.type(editor, ' draft')
    const download = screen.getByRole('button', { name: 'Download editable bundle with referenced files' })
    await user.click(download)
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be downloaded')
    expect(editor).toHaveValue('First revision.\n draft')
    expect(click).not.toHaveBeenCalled()
    await user.click(download)
    await waitFor(() => expect(click).toHaveBeenCalledOnce())
    expect(exportEditableBundle).toHaveBeenCalledWith(undefined)
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:bundle'))
  } finally {
    if (originalCreate) Object.defineProperty(URL, 'createObjectURL', originalCreate)
    else Reflect.deleteProperty(URL, 'createObjectURL')
    if (originalRevoke) Object.defineProperty(URL, 'revokeObjectURL', originalRevoke)
    else Reflect.deleteProperty(URL, 'revokeObjectURL')
    click.mockRestore()
  }
})

it('keeps a denied or conflicting draft and exposes all three versions for review', async () => {
  const user = userEvent.setup()
  const save = vi.fn()
    .mockRejectedValueOnce(new Error('Editing denied'))
    .mockRejectedValueOnce(new RepositoryConflictError({
      reason: 'changed', base: 'Base source', current: 'Current source', proposed: 'My source',
      base_commit: commit, current_commit: 'c'.repeat(40), current_blob: 'd'.repeat(40),
    }))
  setup({ save })
  await user.click(await screen.findByRole('button', { name: /Guide/ }))
  const body = await screen.findByLabelText('Markdown body')
  await user.type(body, ' Local change')
  await user.click(screen.getByRole('button', { name: 'Save to Git' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Editing denied')
  expect(body).toHaveValue('First revision.\n Local change')
  await user.click(screen.getByRole('button', { name: 'Save to Git' }))
  expect(await screen.findByText('Current source')).toBeInTheDocument()
  expect(screen.getByText('Base source')).toBeInTheDocument()
  expect(screen.getByText('My source')).toBeInTheDocument()
  expect(body).toHaveValue('First revision.\n Local change')
})

it('refreshes a new-file base after an unrelated repository advance without discarding its draft', async () => {
  const user = userEvent.setup()
  const advanced = 'c'.repeat(40)
  const list = vi.fn()
    .mockResolvedValueOnce({ results: [], accepted_commit: commit, indexed_commit: commit, count: 0, has_more: false })
    .mockResolvedValue({ results: [], accepted_commit: advanced, indexed_commit: advanced, count: 0, has_more: false })
  const save = vi.fn()
    .mockRejectedValueOnce(new RepositoryConflictError({
      reason: 'repository_changed', base: null, current: null, proposed: null,
      base_commit: commit, current_commit: advanced, current_blob: null,
    }))
    .mockResolvedValue({ ...initial, accepted_commit: advanced, indexed_commit: advanced })
  setup({ list, save })
  await screen.findByText('No repository content matches this search.')
  await user.click(screen.getByRole('button', { name: 'New Markdown file' }))
  await user.type(screen.getByRole('textbox', { name: 'Title' }), 'New guide')
  await user.type(screen.getByLabelText('Markdown body'), 'Keep this draft')
  await user.click(screen.getByRole('button', { name: 'Save to Git' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('The repository changed')
  await user.click(screen.getByRole('button', { name: 'Use current as base and review my draft' }))
  expect(screen.getByLabelText('Markdown body')).toHaveValue('Keep this draft')
  await user.click(screen.getByRole('button', { name: 'Save to Git' }))
  await waitFor(() => expect(save).toHaveBeenLastCalledWith(expect.objectContaining({ base_commit: advanced }), undefined))
})

it('downloads only the loaded saved source, including frontmatter, while a draft is dirty', async () => {
  const user = userEvent.setup()
  const createObjectURL = vi.fn().mockReturnValue('blob:loaded-source')
  const revokeObjectURL = vi.fn()
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.download).toBe('guide.md')
    expect(this.href).toBe('blob:loaded-source')
  })
  const originalCreate = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
  const originalRevoke = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL')
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
  try {
    setup()
    expect(screen.queryByRole('button', { name: 'Download loaded Markdown file' })).not.toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: /Guide/ }))
    expect(screen.getByText(`Loaded Git revision ${commit.slice(0, 12)}. Download includes the saved source and portable metadata, not unsaved edits or other files.`)).toBeInTheDocument()
    await user.type(screen.getByLabelText('Markdown body'), ' Unsaved')
    await user.click(screen.getByRole('button', { name: 'Download loaded Markdown file' }))
    expect(click).toHaveBeenCalledOnce()
    expect(createObjectURL).toHaveBeenCalledOnce()
    const exported = createObjectURL.mock.calls[0][0] as Blob
    expect(exported.type).toBe('text/markdown;charset=utf-8')
    expect(exported.size).toBe(new TextEncoder().encode(initial.source).length)
    const reader = new FileReader()
    const loaded = new Promise<string>((resolve) => { reader.onload = () => resolve(reader.result as string) })
    reader.readAsText(exported)
    expect(await loaded).toBe(initial.source)
    expect(screen.getByLabelText('Markdown body')).toHaveValue('First revision.\n Unsaved')
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:loaded-source'))
  } finally {
    if (originalCreate) Object.defineProperty(URL, 'createObjectURL', originalCreate)
    else Reflect.deleteProperty(URL, 'createObjectURL')
    if (originalRevoke) Object.defineProperty(URL, 'revokeObjectURL', originalRevoke)
    else Reflect.deleteProperty(URL, 'revokeObjectURL')
    click.mockRestore()
  }
})
