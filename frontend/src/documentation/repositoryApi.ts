import { browserAuthClient, browserCsrfToken } from '../auth/api'
import { translate } from '../i18n/localization'
import type { DocumentPrimaryFile } from './api'

export type RepositoryPrimaryFilePage = { results: DocumentPrimaryFile[]; count: number; page: number; page_size: number; has_more: boolean }

export class RepositoryPrimaryFileConflictError extends Error {}

function primaryFile(value: unknown): DocumentPrimaryFile {
  if (!value || typeof value !== 'object') throw new Error('Invalid primary-file response')
  const row = value as Record<string, unknown>
  const uuid = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/i
  if (typeof row.id !== 'string' || !uuid.test(row.id)
    || typeof row.filename !== 'string' || !row.filename || row.filename.length > 255
    || typeof row.size !== 'number' || !Number.isSafeInteger(row.size) || row.size < 0
    || typeof row.version_number !== 'number' || !Number.isSafeInteger(row.version_number) || row.version_number < 1
    || (row.replaces_id !== null && (typeof row.replaces_id !== 'string' || !uuid.test(row.replaces_id)))
    || ((row.version_number === 1) !== (row.replaces_id === null)) || row.replaces_id === row.id
    || typeof row.is_current !== 'boolean' || row.scan_status !== 'clean'
    || typeof row.checksum !== 'string' || !/^[a-f0-9]{64}$/.test(row.checksum)
    || !['media_type', 'scan_engine', 'scanned_at', 'created_at'].every(key => typeof row[key] === 'string' && row[key])) {
    throw new Error('Invalid primary-file response')
  }
  return row as DocumentPrimaryFile
}

export type RepositorySummary = {
  id: string
  title: string
  kind: 'document' | 'fragment'
  path: string
}

export type RepositoryListing = {
  results: RepositorySummary[]
  accepted_commit: string | null
  indexed_commit: string | null
  count: number
  has_more: boolean
}

export type RepositorySource = {
  content_id: string
  path: string
  kind: 'document' | 'fragment'
  title: string
  markdown: string
  source: string
  source_blob: string
  accepted_commit: string | null
  indexed_commit: string | null
}

export type RepositoryAttachment = {
  id: string
  filename: string
  size: number
  scan_status: 'clean'
}

export type RepositoryAttachmentStatus = {
  id: string
  filename: string
  size: number
  linked_current: boolean
  can_archive: boolean
}

export type RepositoryAttachmentPage = {
  results: RepositoryAttachmentStatus[]
  page: number
  page_size: number
  count: number
  has_more: boolean
}

export type RepositoryEvidence = {
  id: string
  content_id: string
  audience: string
  title: string
  source_commit: string
  signed_at: string
}

export type RepositoryEvidencePage = {
  results: RepositoryEvidence[]
  page: number
  page_size: number
  count: number
  has_more: boolean
}

export type RepositoryStaticPublication = {
  id: string
  source_commit: string
  content_digest: string
  verified: boolean
  permits_distribution: boolean
}

export type RepositoryStaticFormat = 'md' | 'html' | 'pdf'

export type RepositoryPublicationAction = 'accept_review' | 'reject_review' | 'create_package' | 'authorize_package' | 'reject_package' | 'create_static' | 'release_client' | 'withdraw_client' | 'authorize_delivery' | 'release_internal' | 'withdraw_internal'

export type RepositoryWorkflow = {
  evidence_id: string
  source_commit: string
  audience: string
  verified: boolean
  stage: string
  state: string
  actions: RepositoryPublicationAction[]
  active_publication_id: string | null
  publication_id: string | null
  content_digest: string
  delivery_effective: boolean
  events: { id: string; action: string; supersedes_id: string | null; reason: string; actor_id: string; occurred_at: string }[]
}

export type RepositoryMutation = {
  operation: 'create' | 'update' | 'move'
  content_id: string
  base_commit: string | null
  base_blob?: string | null
  kind?: 'document' | 'fragment'
  path?: string | null
  title?: string
  markdown?: string
  metadata_patch?: Record<string, unknown>
}

export type RepositoryConflict = {
  reason: string
  base: string | null
  current: string | null
  proposed: string | null
  base_commit: string | null
  current_commit: string | null
  current_blob: string | null
}

export class RepositoryConflictError extends Error {
  constructor(public readonly conflict: RepositoryConflict) {
    super('Repository source changed')
  }
}

export class RepositoryRecentAuthenticationRequiredError extends Error {}

function path(organizationId?: string) {
  return organizationId
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(organizationId)}/content-graph`
    : '/api/v1/workspaces/msp/content-graph'
}

function evidencePath(organizationId?: string) {
  return organizationId
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(organizationId)}/repository-publication-evidence`
    : '/api/v1/workspaces/msp/repository-publication-evidence'
}

async function token() {
  let value = browserCsrfToken()
  if (!value) {
    await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    value = browserCsrfToken()
  }
  if (!value) throw new Error(translate('repository.tokenUnavailable'))
  return value
}

async function parse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>
  if (response.status === 409) throw new RepositoryConflictError(await response.json() as RepositoryConflict)
  let detail: unknown
  try {
    const body = await response.json() as { detail?: unknown; error?: { code?: unknown } }
    if (response.status === 403 && body.error?.code === 'recent_authentication_required') throw new RepositoryRecentAuthenticationRequiredError()
    detail = body.detail
  } catch (error) {
    if (error instanceof RepositoryRecentAuthenticationRequiredError) throw error
    /* An upstream error may be HTML. */
  }
  throw new Error(typeof detail === 'string' && detail.length < 300 ? detail : translate('repository.requestFailed', { status: response.status }))
}

export const browserRepositoryClient = {
  async primaryFiles(contentId: string, organizationId?: string, page = 1, signal?: AbortSignal): Promise<RepositoryPrimaryFilePage> {
    const response = await fetch(path(organizationId) + '/authoring/' + encodeURIComponent(contentId) + '/primary-file?page=' + page, {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
    })
    const result = await parse<RepositoryPrimaryFilePage>(response)
    if (!Array.isArray(result.results) || result.page !== page || result.page_size !== 25
      || !Number.isSafeInteger(result.count) || result.count < 0 || typeof result.has_more !== 'boolean') throw new Error('Invalid primary-file history')
    const results = result.results.map(primaryFile)
    if (results.length !== Math.min(25, Math.max(0, result.count - (page - 1) * 25))
      || result.has_more !== (page * 25 < result.count)
      || results.some((row, index) => row.version_number !== result.count - (page - 1) * 25 - index
        || row.is_current !== (page === 1 && index === 0))) throw new Error('Invalid primary-file history')
    return { ...result, results }
  },
  async appendPrimaryFile(contentId: string, file: File, expectedCurrentId: string | null, organizationId?: string, signal?: AbortSignal): Promise<DocumentPrimaryFile> {
    const form = new FormData()
    form.set('file', file)
    if (expectedCurrentId !== null) form.set('expected_current_id', expectedCurrentId)
    const response = await fetch(path(organizationId) + '/authoring/' + encodeURIComponent(contentId) + '/primary-file', {
      method: 'POST', credentials: 'same-origin', signal,
      headers: { Accept: 'application/json', 'X-CSRFToken': await token() }, body: form,
    })
    if (response.status === 409) throw new RepositoryPrimaryFileConflictError('Current primary file changed')
    return primaryFile(await parse<unknown>(response))
  },
  primaryFileDownloadUrl(contentId: string, fileId: string, organizationId?: string) {
    return path(organizationId) + '/documents/' + encodeURIComponent(contentId) + '/attachments/' + encodeURIComponent(fileId) + '/download'
  },
  async downloadPrimaryFile(contentId: string, version: DocumentPrimaryFile, organizationId?: string, signal?: AbortSignal): Promise<{ content: Blob; name: string }> {
    const response = await fetch(browserRepositoryClient.primaryFileDownloadUrl(contentId, version.id, organizationId), { credentials: 'same-origin', signal })
    if (response.status !== 200 || response.headers.get('Content-Type') !== 'application/octet-stream'
      || !response.headers.get('Content-Disposition')?.startsWith('attachment;')
      || response.headers.get('Cache-Control') !== 'private, no-store'
      || response.headers.get('X-Content-Type-Options') !== 'nosniff') throw new Error(translate('repository.primary.downloadFailed'))
    const bytes = await response.arrayBuffer()
    if (bytes.byteLength !== version.size) throw new Error(translate('repository.primary.downloadFailed'))
    return { content: new Blob([bytes], { type: 'application/octet-stream' }), name: version.filename }
  },
  reauthenticate: (password: string) => browserAuthClient.reauthenticate(password),
  async createEvidence(contentId: string, audience: string, expectedCommit: string, organizationId?: string, signal?: AbortSignal) {
    return parse<RepositoryEvidence>(await fetch(evidencePath(organizationId), {
      method: 'POST', credentials: 'same-origin', signal,
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': await token() },
      body: JSON.stringify({ content_id: contentId, audience, expected_commit: expectedCommit }),
    }))
  },
  async publicationWorkflow(evidenceId: string, organizationId?: string, signal?: AbortSignal) {
    return parse<RepositoryWorkflow>(await fetch(`${evidencePath(organizationId)}/${encodeURIComponent(evidenceId)}/workflow`, {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
    }))
  },
  async publicationAction(evidenceId: string, action: RepositoryPublicationAction, reason: string, supersedesId: string | null, organizationId?: string, signal?: AbortSignal) {
    const actions: Record<RepositoryPublicationAction, { suffix: string; body: Record<string, unknown> }> = {
      accept_review: { suffix: '/decision', body: { outcome: 'accepted_for_packaging', reason } },
      reject_review: { suffix: '/decision', body: { outcome: 'rejected', reason } },
      create_package: { suffix: '/package', body: {} },
      authorize_package: { suffix: '/package/authorization', body: { outcome: 'authorized_for_publication', reason } },
      reject_package: { suffix: '/package/authorization', body: { outcome: 'rejected', reason } },
      create_static: { suffix: '/package/static-publication', body: {} },
      release_client: { suffix: '/package/static-publication/control', body: { action: 'released', reason, supersedes_id: supersedesId } },
      withdraw_client: { suffix: '/package/static-publication/control', body: { action: 'withdrawn', reason } },
      authorize_delivery: { suffix: '/package/static-publication/delivery-authorization', body: { reason } },
      release_internal: { suffix: '/internal-publication', body: { action: 'released', reason, supersedes_id: supersedesId } },
      withdraw_internal: { suffix: '/internal-publication', body: { action: 'withdrawn', reason } },
    }
    const operation = actions[action]
    await parse<unknown>(await fetch(`${evidencePath(organizationId)}/${encodeURIComponent(evidenceId)}${operation.suffix}`, {
      method: 'POST', credentials: 'same-origin', signal,
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': await token() }, body: JSON.stringify(operation.body),
    }))
  },
  async internalPublicationPdf(evidenceId: string, expectedDigest: string, organizationId?: string, signal?: AbortSignal) {
    const response = await fetch(`${evidencePath(organizationId)}/${encodeURIComponent(evidenceId)}/internal-publication/pdf`, { credentials: 'same-origin', signal })
    if (!response.ok || !/^[a-f0-9]{64}$/.test(expectedDigest)
      || response.headers.get('X-TekDocs-Publication-Digest') !== expectedDigest
      || response.headers.get('X-TekDocs-Export-Class') !== 'immutable_internal_publication'
      || response.headers.get('Content-Type') !== 'application/pdf'
      || response.headers.get('Content-Disposition') !== 'attachment; filename="repository-internal-publication.pdf"'
      || response.headers.get('Cache-Control') !== 'private, no-store'
      || response.headers.get('X-Content-Type-Options') !== 'nosniff') throw new Error(translate('repository.lifecycle.downloadFailed'))
    const bytes = await response.arrayBuffer()
    if (bytes.byteLength > 8 * 1024 * 1024 || new TextDecoder().decode(bytes.slice(0, 5)) !== '%PDF-') throw new Error(translate('repository.lifecycle.downloadFailed'))
    return { content: new Blob([bytes], { type: 'application/pdf' }), name: 'repository-internal-publication.pdf' }
  },
  async list(organizationId?: string, q = '', signal?: AbortSignal) {
    const query = new URLSearchParams({ page_size: '100' })
    if (q) query.set('q', q)
    const response = await fetch(`${path(organizationId)}/documents?${query}`, {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
    })
    return parse<RepositoryListing>(response)
  },
  async source(contentId: string, organizationId?: string, signal?: AbortSignal) {
    const response = await fetch(`${path(organizationId)}/authoring/${encodeURIComponent(contentId)}`, {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
    })
    return parse<RepositorySource>(response)
  },
  async listEvidence(contentId: string, organizationId?: string, page = 1, signal?: AbortSignal) {
    const query = new URLSearchParams({ content_id: contentId, page: String(page), page_size: '25' })
    const response = await fetch(`${evidencePath(organizationId)}?${query}`, {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
    })
    return parse<RepositoryEvidencePage>(response)
  },
  async staticPublication(evidenceId: string, organizationId?: string, signal?: AbortSignal) {
    const response = await fetch(`${evidencePath(organizationId)}/${encodeURIComponent(evidenceId)}/package/static-publication`, {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
    })
    if (response.status === 404 || response.status === 409) return null
    return parse<RepositoryStaticPublication>(response)
  },
  async reviewPdf(evidenceId: string, organizationId?: string, signal?: AbortSignal) {
    const response = await fetch(`${evidencePath(organizationId)}/${encodeURIComponent(evidenceId)}/review/pdf`, {
      credentials: 'same-origin', signal,
    })
    if (!response.ok
      || response.headers.get('Content-Type') !== 'application/pdf'
      || response.headers.get('Content-Disposition') !== 'attachment; filename="repository-evidence-snapshot.pdf"'
      || response.headers.get('Cache-Control') !== 'private, no-store'
      || response.headers.get('X-Content-Type-Options') !== 'nosniff') {
      throw new Error(translate('repository.reviewPdfFailed'))
    }
    const bytes = await response.arrayBuffer()
    if (bytes.byteLength < 5 || bytes.byteLength > 8 * 1024 * 1024
      || new TextDecoder().decode(bytes.slice(0, 5)) !== '%PDF-') {
      throw new Error(translate('repository.reviewPdfFailed'))
    }
    return { content: new Blob([bytes], { type: 'application/pdf' }), name: 'repository-evidence-snapshot.pdf' }
  },
  async exportStatic(evidenceId: string, format: RepositoryStaticFormat, expectedDigest: string, organizationId?: string, signal?: AbortSignal) {
    if (!organizationId) throw new Error(translate('repository.staticDownloadFailed'))
    const endpoint = format === 'md' ? 'markdown' : format
    const response = await fetch(`${evidencePath(organizationId)}/${encodeURIComponent(evidenceId)}/package/static-publication/export/${endpoint}`, {
      credentials: 'same-origin', signal,
    })
    if (!response.ok) throw new Error(translate('repository.staticDownloadFailed'))
    const mediaType = format === 'md' ? 'text/markdown' : format === 'html' ? 'text/html' : 'application/pdf'
    const digest = response.headers.get('X-TekDocs-Publication-Digest')
    if (!/^[a-f0-9]{64}$/.test(expectedDigest)
      || digest !== expectedDigest
      || response.headers.get('X-TekDocs-Export-Class') !== 'immutable_static_publication'
      || !response.headers.get('Content-Type')?.startsWith(mediaType)
      || response.headers.get('Content-Disposition') !== `attachment; filename="repository-static-publication.${format}"`
      || response.headers.get('X-Content-Type-Options') !== 'nosniff'
      || response.headers.get('Cache-Control') !== 'private, no-store'
      || (format === 'html' && response.headers.get('Content-Security-Policy') !== "sandbox; default-src 'none'")) {
      throw new Error(translate('repository.staticDownloadFailed'))
    }
    const content = await response.blob()
    if (content.size > 8 * 1024 * 1024) throw new Error(translate('repository.staticDownloadFailed'))
    return { content, name: `repository-static-publication.${format}` }
  },
  async exportSources(organizationId?: string) {
    const response = await fetch(`${path(organizationId)}/authoring/export`, {
      credentials: 'same-origin',
    })
    if (!response.ok) {
      let detail: unknown
      try { detail = (await response.json() as { detail?: unknown }).detail } catch { /* Upstream errors may be HTML. */ }
      throw new Error(typeof detail === 'string' && detail.length < 300 ? detail : translate('repository.requestFailed', { status: response.status }))
    }
    if (!response.headers.get('Content-Type')?.startsWith('application/zip')) throw new Error(translate('repository.snapshotFailed'))
    const disposition = response.headers.get('Content-Disposition') || ''
    const name = disposition.match(/filename="(tekdocs-repository-[a-f0-9]{12}\.zip)"/)?.[1] || 'tekdocs-repository-source.zip'
    return { content: await response.blob(), name }
  },
  async exportEditableBundle(organizationId?: string) {
    const response = await fetch(`${path(organizationId)}/authoring/export?bundle=editable`, {
      credentials: 'same-origin',
    })
    if (!response.ok) {
      let detail: unknown
      try { detail = (await response.json() as { detail?: unknown }).detail } catch { /* Upstream errors may be HTML. */ }
      throw new Error(typeof detail === 'string' && detail.length < 300 ? detail : translate('repository.bundleFailed'))
    }
    const disposition = response.headers.get('Content-Disposition') || ''
    const match = disposition.match(/^attachment; filename="(tekdocs-repository-editable-[a-f0-9]{12}\.zip)"$/)
    if (!response.headers.get('Content-Type')?.startsWith('application/zip')
      || response.headers.get('X-Content-Type-Options') !== 'nosniff'
      || response.headers.get('Cache-Control') !== 'no-store'
      || !match) throw new Error(translate('repository.bundleFailed'))
    const content = await response.blob()
    if (content.size > 75 * 1024 * 1024) throw new Error(translate('repository.bundleFailed'))
    return { content, name: match[1] }
  },
  async exportHtml(contentId: string, organizationId?: string) {
    const response = await fetch(`${path(organizationId)}/documents/${encodeURIComponent(contentId)}/export/html`, {
      credentials: 'same-origin',
    })
    if (!response.ok) throw new Error(translate('repository.htmlFailed'))
    const commit = response.headers.get('X-TekDocs-Repository-Commit')
    if (!response.headers.get('Content-Type')?.startsWith('text/html')
      || response.headers.get('X-TekDocs-Export-Class') !== 'live_repository_revision'
      || !commit || !/^[a-f0-9]{40}$|^[a-f0-9]{64}$/.test(commit)
      || response.headers.get('Content-Disposition') !== 'attachment; filename="repository-document.html"') {
      throw new Error(translate('repository.htmlFailed'))
    }
    return { content: await response.blob(), name: 'repository-document.html', commit }
  },
  async exportPdf(contentId: string, organizationId?: string) {
    const response = await fetch(`${path(organizationId)}/documents/${encodeURIComponent(contentId)}/export/pdf`, {
      credentials: 'same-origin',
    })
    if (!response.ok) throw new Error(translate('repository.pdfFailed'))
    const commit = response.headers.get('X-TekDocs-Repository-Commit')
    if (response.headers.get('Content-Type') !== 'application/pdf'
      || response.headers.get('Content-Disposition') !== 'attachment; filename="repository-document.pdf"'
      || response.headers.get('X-TekDocs-Export-Class') !== 'live_repository_revision'
      || !commit || !/^(?:[a-f0-9]{40}|[a-f0-9]{64})$/.test(commit)
      || response.headers.get('Cache-Control') !== 'private, no-store'
      || response.headers.get('X-Content-Type-Options') !== 'nosniff') {
      throw new Error(translate('repository.pdfFailed'))
    }
    const bytes = await response.arrayBuffer()
    if (bytes.byteLength < 5 || bytes.byteLength > 8 * 1024 * 1024
      || new TextDecoder().decode(bytes.slice(0, 5)) !== '%PDF-') {
      throw new Error(translate('repository.pdfFailed'))
    }
    return { content: new Blob([bytes], { type: 'application/pdf' }), name: 'repository-document.pdf', commit }
  },
  async exportDocx(contentId: string, organizationId?: string) {
    const response = await fetch(`${path(organizationId)}/documents/${encodeURIComponent(contentId)}/export/docx`, {
      credentials: 'same-origin',
    })
    if (!response.ok) throw new Error(translate('repository.docxFailed'))
    const commit = response.headers.get('X-TekDocs-Repository-Commit')
    const mediaType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    if (response.headers.get('Content-Type') !== mediaType
      || response.headers.get('Content-Disposition') !== 'attachment; filename="repository-document.docx"'
      || response.headers.get('X-TekDocs-Export-Class') !== 'live_repository_revision'
      || !commit || !/^(?:[a-f0-9]{40}|[a-f0-9]{64})$/.test(commit)
      || response.headers.get('Cache-Control') !== 'private, no-store'
      || response.headers.get('X-Content-Type-Options') !== 'nosniff') {
      throw new Error(translate('repository.docxFailed'))
    }
    const bytes = await response.arrayBuffer()
    const signature = new Uint8Array(bytes, 0, Math.min(bytes.byteLength, 4))
    if (bytes.byteLength < 4 || bytes.byteLength > 8 * 1024 * 1024
      || signature[0] !== 0x50 || signature[1] !== 0x4b || signature[2] !== 0x03 || signature[3] !== 0x04) {
      throw new Error(translate('repository.docxFailed'))
    }
    return { content: new Blob([bytes], { type: mediaType }), name: 'repository-document.docx', commit }
  },
  async save(mutation: RepositoryMutation, organizationId?: string) {
    const response = await fetch(`${path(organizationId)}/authoring`, {
      method: 'POST', credentials: 'same-origin',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': await token() },
      body: JSON.stringify(mutation),
    })
    return parse<RepositorySource>(response)
  },
  async uploadAttachment(contentId: string, file: File, organizationId?: string): Promise<RepositoryAttachment> {
    const form = new FormData()
    form.set('file', file)
    const response = await fetch(`${path(organizationId)}/authoring/${encodeURIComponent(contentId)}/attachments`, {
      method: 'POST', credentials: 'same-origin',
      headers: { Accept: 'application/json', 'X-CSRFToken': await token() },
      body: form,
    })
    if (!response.ok) {
      let detail: unknown
      try { detail = (await response.json() as { detail?: unknown }).detail } catch { /* An upstream error may be HTML. */ }
      throw new Error(typeof detail === 'string' && detail.length < 300 ? detail : translate('repository.attachmentFailed'))
    }
    const result: unknown = await response.json()
    if (!result || typeof result !== 'object') throw new Error(translate('repository.attachmentFailed'))
    const attachment = result as Record<string, unknown>
    if (typeof attachment.id !== 'string' || !/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/i.test(attachment.id)
      || typeof attachment.filename !== 'string' || !attachment.filename || attachment.filename.length > 255
      || typeof attachment.size !== 'number' || !Number.isSafeInteger(attachment.size) || attachment.size < 0
      || attachment.scan_status !== 'clean') throw new Error(translate('repository.attachmentFailed'))
    return attachment as RepositoryAttachment
  },
  async listAttachments(contentId: string, organizationId?: string, page = 1, signal?: AbortSignal) {
    const query = new URLSearchParams({ page: String(page) })
    const response = await fetch(`${path(organizationId)}/authoring/${encodeURIComponent(contentId)}/attachments?${query}`, {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
    })
    return parse<RepositoryAttachmentPage>(response)
  },
  async archiveAttachment(contentId: string, attachmentId: string, organizationId?: string) {
    const response = await fetch(`${path(organizationId)}/authoring/${encodeURIComponent(contentId)}/attachments/${encodeURIComponent(attachmentId)}`, {
      method: 'DELETE', credentials: 'same-origin',
      headers: { Accept: 'application/json', 'X-CSRFToken': await token() },
    })
    if (response.status === 204) return
    await parse<unknown>(response)
  },
}

export type RepositoryClient = typeof browserRepositoryClient
