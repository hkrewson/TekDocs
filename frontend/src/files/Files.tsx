import { useEffect, useMemo, useState } from 'react'
import { Download, ExternalLink, Search } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'

import type { DocumentAttachment, DocumentPrimaryFile, DocumentRecord, DocumentsClient } from '../documentation/api'
import { formatDateTime, formatInteger, translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'

type ManagedFile = {
  id: string
  documentId: string
  documentTitle: string
  file: DocumentAttachment | DocumentPrimaryFile
  kind: 'Primary file' | 'Attachment'
  version: number | null
}

function managedFiles(documents: DocumentRecord[]): ManagedFile[] {
  return documents.flatMap((document) => [
    ...document.primary_file_versions.map((file) => ({
      id: file.id,
      documentId: document.id,
      documentTitle: document.title,
      file,
      kind: 'Primary file' as const,
      version: file.version_number,
    })),
    ...document.attachments.map((file) => ({
      id: file.id,
      documentId: document.id,
      documentTitle: document.title,
      file,
      kind: 'Attachment' as const,
      version: null,
    })),
  ]).sort((left, right) => right.file.created_at.localeCompare(left.file.created_at))
}

function documentPath(workspace: WorkspaceContext | null, documentId: string) {
  const base = workspace
    ? `/workspaces/organizations/${encodeURIComponent(workspace.id)}/documentation`
    : '/documentation'
  return `${base}?document=${encodeURIComponent(documentId)}`
}

export function Files({ workspace, client }: { workspace: WorkspaceContext | null; client: DocumentsClient }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState(() => searchParams.get('q') ?? '')
  const [documents, setDocuments] = useState<DocumentRecord[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const scope = useMemo(() => workspace ? { organizationId: workspace.id } : {}, [workspace])

  useEffect(() => {
    const controller = new AbortController()
    client.list(scope, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setDocuments(result.results) })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : translate('files.loadFailed'))
      })
    return () => controller.abort()
  }, [client, scope])

  const files = useMemo(() => managedFiles(documents ?? []), [documents])
  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return files
    return files.filter((item) => [item.file.filename, item.documentTitle, item.file.media_type, item.kind]
      .some((value) => value.toLowerCase().includes(normalized)))
  }, [files, query])

  function updateQuery(value: string) {
    setQuery(value)
    const next = new URLSearchParams(searchParams)
    if (value.trim()) next.set('q', value)
    else next.delete('q')
    setSearchParams(next, { replace: true })
  }

  return <>
    <header className="page-header"><div><h1>{translate('files.heading')}</h1><p>{translate('files.intro')}</p></div></header>
    {error && <p className="form-error" role="alert">{error}</p>}
    <section className="content-section" aria-labelledby="managed-files-heading">
      <div className="section-heading exposure-heading">
        <div><h2 id="managed-files-heading">{translate('files.managed')}</h2><p>{translate('files.scope')}</p></div>
        <label className="exposure-search"><Search size={16} aria-hidden="true" /><span className="sr-only">{translate('files.search')}</span><input type="search" value={query} placeholder={translate('files.search')} onChange={(event) => updateQuery(event.target.value)} /></label>
      </div>
      {documents === null && !error ? <p role="status">{translate('files.loading')}</p>
        : visible.length === 0 ? <p className="empty-state">{query ? translate('files.noMatches') : translate('files.empty')}</p>
          : <div className="network-table-wrap" role="group" aria-label={translate('files.table')} tabIndex={0}>
            <table className="network-table"><caption className="sr-only">{translate('files.table')}</caption><thead><tr><th>{translate('files.filename')}</th><th>{translate('files.document')}</th><th>{translate('files.kind')}</th><th>{translate('files.type')}</th><th>{translate('files.size')}</th><th>{translate('files.added')}</th><th><span className="sr-only">{translate('common.actions')}</span></th></tr></thead>
              <tbody>{visible.map((item) => <tr key={`${item.documentId}:${item.id}`}><td><strong>{item.file.filename}</strong><small>{item.file.checksum.slice(0, 12)}</small></td><td><Link to={documentPath(workspace, item.documentId)}>{item.documentTitle} <ExternalLink size={12} aria-hidden="true" /></Link></td><td>{item.kind}{item.version ? ` · ${translate('files.version', { version: item.version })}` : ''}</td><td>{item.file.media_type}</td><td>{formatInteger(item.file.size)} B</td><td>{formatDateTime(item.file.created_at)}</td><td><a className="secondary-button compact-button" href={client.attachmentDownloadUrl(scope, item.documentId, item.id)}><Download size={14} aria-hidden="true" />{translate('files.download')}</a></td></tr>)}</tbody>
            </table>
          </div>}
    </section>
  </>
}
