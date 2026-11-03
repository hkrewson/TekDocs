import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { DocumentPrimaryFile } from './api'
import { RepositoryPrimaryFileConflictError, type RepositoryClient } from './repositoryApi'

export function RepositoryPrimaryFiles({ contentId, organizationId, client, canWrite, onEditingChange }: {
  contentId: string; organizationId?: string; client: RepositoryClient; canWrite: boolean
  onEditingChange: (editing: boolean) => void
}) {
  const headingId = useId()
  const [open, setOpen] = useState(false)
  const [versions, setVersions] = useState<DocumentPrimaryFile[]>([])
  const [page, setPage] = useState(1)
  const [more, setMore] = useState(false)
  const [ready, setReady] = useState(false)
  const [loading, setLoading] = useState(false)
  const [operation, setOperation] = useState<'upload' | 'download' | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [confirmedId, setConfirmedId] = useState<string | undefined>()
  const [needsRefresh, setNeedsRefresh] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const request = useRef<AbortController | null>(null)
  const mutation = useRef<AbortController | null>(null)
  const total = useRef<number | null>(null)
  const current = versions.find(version => version.is_current)
  const busy = operation !== null
  useUnsavedChanges(file !== null, busy, () => { setFile(null); setConfirmedId(undefined) }, file !== null)
  useEffect(() => { onEditingChange(file !== null || busy) }, [file, busy, onEditingChange])
  useEffect(() => () => { request.current?.abort(); mutation.current?.abort(); onEditingChange(false) }, [onEditingChange])

  const load = useCallback(async (selectedPage = 1) => {
    request.current?.abort()
    const controller = new AbortController(); request.current = controller
    setLoading(true); setError(''); setConfirmedId(undefined)
    try {
      const result = await client.primaryFiles(contentId, organizationId, selectedPage, controller.signal)
      if (controller.signal.aborted) return
      if (selectedPage > 1 && result.count !== total.current) throw new RepositoryPrimaryFileConflictError()
      total.current = result.count
      setVersions(previous => selectedPage === 1 ? result.results : [...previous, ...result.results])
      setPage(selectedPage); setMore(result.has_more); setReady(true); setNeedsRefresh(false)
    } catch (caught) {
      if (!controller.signal.aborted) {
        setReady(false); setVersions([]); setMore(false)
        setError(translate(caught instanceof RepositoryPrimaryFileConflictError ? 'repository.primary.historyChanged' : 'repository.primary.loadFailed'))
      }
    } finally { if (!controller.signal.aborted) setLoading(false) }
  }, [client, contentId, organizationId])

  async function upload() {
    if (!file || !canWrite || !ready || loading || busy || needsRefresh || (current && confirmedId !== current.id)) return
    const controller = new AbortController(); mutation.current = controller
    setOperation('upload'); setError(''); setMessage('')
    try {
      const result = await client.appendPrimaryFile(contentId, file, current?.id ?? null, organizationId, controller.signal)
      if (controller.signal.aborted) return
      if (!result.is_current || result.replaces_id !== (current?.id ?? null)
        || result.version_number !== (current?.version_number ?? 0) + 1) throw new Error('Primary-file lineage changed')
      setFile(null); setConfirmedId(undefined); setMessage(translate('repository.primary.uploaded'))
      await load()
    } catch (caught) {
      if (!controller.signal.aborted) {
        setNeedsRefresh(true); setConfirmedId(undefined)
        setError(translate(caught instanceof RepositoryPrimaryFileConflictError ? 'repository.primary.conflict' : 'repository.primary.uploadFailed'))
      }
    } finally { if (!controller.signal.aborted) setOperation(null) }
  }

  async function download(version: DocumentPrimaryFile) {
    if (busy || loading) return
    const controller = new AbortController(); mutation.current = controller
    setOperation('download'); setError('')
    try {
      const result = await client.downloadPrimaryFile(contentId, version, organizationId, controller.signal)
      if (controller.signal.aborted) return
      const url = URL.createObjectURL(result.content)
      const link = document.createElement('a'); link.href = url; link.download = result.name; link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch { if (!controller.signal.aborted) setError(translate('repository.primary.downloadFailed')) }
    finally { if (!controller.signal.aborted) setOperation(null) }
  }

  if (!open) return <button type="button" className="secondary-button" onClick={() => { setOpen(true); void load() }}>{translate('repository.primary.heading')}</button>
  return <section className="document-files primary-file-history" aria-labelledby={headingId}>
    <div className="section-heading"><h2 id={headingId}>{translate('repository.primary.heading')}</h2>
      <button type="button" className="secondary-button" disabled={file !== null || busy || loading} onClick={() => setOpen(false)}>{translate('common.close')}</button>
    </div>
    {loading && <p role="status">{translate('repository.primary.loading')}</p>}
    {operation && <p role="status">{translate(operation === 'upload' ? 'repository.primary.uploading' : 'repository.primary.downloading')}</p>}
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    <button type="button" className="secondary-button" disabled={loading || busy} onClick={() => { void load() }}>{translate('repository.primary.refresh')}</button>
    {ready && versions.length === 0 && <p>{translate('repository.primary.empty')}</p>}
    <ul>{versions.map(version => <li key={version.id}>
      <span><strong>{version.filename}</strong><small>{translate(version.is_current ? 'documentation.currentFileVersion' : 'documentation.retainedFileVersion', { version: version.version_number, size: version.size.toLocaleString() })}</small></span>
      <button type="button" className="secondary-button" disabled={loading || busy} onClick={() => { void download(version) }} aria-label={translate('repository.primary.download', { filename: version.filename, version: version.version_number })}>{translate('files.download')}</button>
    </li>)}</ul>
    {more && <button type="button" className="secondary-button" disabled={loading || busy || needsRefresh} onClick={() => { void load(page + 1) }}>{translate('repository.primary.more')}</button>}
    <label>{translate('repository.primary.choose')}<input type="file" disabled={!canWrite || !ready || loading || busy} onChange={event => {
      const selected = event.currentTarget.files?.[0]; event.currentTarget.value = ''
      if (selected) { setFile(selected); setConfirmedId(undefined); setMessage('') }
    }} /></label>
    {file && <>
      <p>{translate('repository.primary.selected', { filename: file.name })}</p>
      {current && <label><input type="checkbox" checked={confirmedId === current.id} disabled={loading || busy || needsRefresh} onChange={event => setConfirmedId(event.target.checked ? current.id : undefined)} />{translate('repository.primary.confirm', { version: current.version_number })}</label>}
      <div className="form-actions"><button type="button" className="primary-button" disabled={!canWrite || !ready || loading || busy || needsRefresh || (!!current && confirmedId !== current.id)} onClick={() => { void upload() }}>{translate(current ? 'repository.primary.replace' : 'repository.primary.upload')}</button>
        <button type="button" className="secondary-button" disabled={busy} onClick={() => { setFile(null); setConfirmedId(undefined) }}>{translate('repository.primary.cancel')}</button></div>
    </>}
  </section>
}
