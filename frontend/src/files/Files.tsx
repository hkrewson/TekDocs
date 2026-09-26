import { Download } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { CollectionPagination } from '../CollectionPagination'
import { CollectionTable } from '../collections/CollectionTable'
import { ColumnChooser } from '../collections/ColumnChooser'
import { browserCollectionPreferences, defaultPreferences } from '../collections/preferences'
import type { CollectionPreferences } from '../collections/preferences'
import { browserDocumentsClient } from '../documentation/api'
import type { DocumentFile, DocumentFileQuery, DocumentFileResult, DocumentsClient } from '../documentation/api'
import { FilterMenu } from '../FilterMenu'
import { formatDateTime, formatInteger, translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import '../collections/collections.css'

const columns = ['name', 'document', 'kind', 'type', 'size', 'added'] as const
const labels = {
  name: translate('files.filename'), document: translate('files.document'), kind: translate('files.kind'),
  type: translate('files.type'), size: translate('files.size'), added: translate('files.added'),
}
const orderingFields = { name: 'filename', document: 'document', kind: 'kind', type: 'type', size: 'size', added: 'created_at' } as const

function documentPath(workspace: WorkspaceContext | null, documentId: string) {
  const base = workspace ? `/workspaces/organizations/${encodeURIComponent(workspace.id)}/documentation` : '/documentation'
  return `${base}?document=${encodeURIComponent(documentId)}`
}

function tableOrdering(ordering: string) {
  const descending = ordering.startsWith('-')
  const field = ordering.replace(/^-/, '')
  const column = Object.entries(orderingFields).find(([, value]) => value === field)?.[0] ?? 'added'
  return descending ? `-${column}` : column
}

function apiOrdering(ordering: string): NonNullable<DocumentFileQuery['ordering']> {
  const descending = ordering.startsWith('-')
  const column = ordering.replace(/^-/, '') as keyof typeof orderingFields
  return `${descending ? '-' : ''}${orderingFields[column] ?? 'created_at'}` as NonNullable<DocumentFileQuery['ordering']>
}

export function Files({ workspace, preferenceWorkspace, client = browserDocumentsClient, preferenceClient = browserCollectionPreferences }: {
  workspace: WorkspaceContext | null
  preferenceWorkspace?: WorkspaceContext
  client?: DocumentsClient
  preferenceClient?: typeof browserCollectionPreferences
}) {
  const [params, setParams] = useSearchParams()
  const [preferences, setPreferences] = useState<CollectionPreferences>(() => defaultPreferences(columns))
  const [response, setResponse] = useState<{ key: string; result?: DocumentFileResult } | null>(null)
  const [reload, setReload] = useState(0)
  const [preferenceError, setPreferenceError] = useState('')
  const scope = useMemo(() => workspace ? { organizationId: workspace.id } : {}, [workspace])
  const requestedPage = Number(params.get('page') ?? 1)
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  const pageSize = [25, 50, 100].includes(Number(params.get('page_size'))) ? Number(params.get('page_size')) as 25 | 50 | 100 : preferences.page_size
  const query = useMemo<DocumentFileQuery>(() => ({
    q: params.get('q') ?? '', kind: (params.get('kind') ?? '') as DocumentFileQuery['kind'],
    ordering: (params.get('ordering') ?? '-created_at') as DocumentFileQuery['ordering'], page, page_size: pageSize,
  }), [params, page, pageSize])
  const key = `${workspace?.id ?? 'msp'}:${JSON.stringify(query)}`
  const result = response?.key === key ? response.result : null

  useEffect(() => {
    if (!preferenceWorkspace) return
    const controller = new AbortController()
    preferenceClient.load(preferenceWorkspace, 'files', columns, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setPreferences(value) })
      .catch(() => { if (!controller.signal.aborted) setPreferences(defaultPreferences(columns)) })
    return () => controller.abort()
  }, [preferenceClient, preferenceWorkspace])

  useEffect(() => {
    const controller = new AbortController()
    client.listFiles(scope, query, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setResponse({ key, result: value }) })
      .catch(() => { if (!controller.signal.aborted) setResponse({ key }) })
    return () => controller.abort()
  }, [client, scope, query, key, reload])

  function browse(values: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    for (const [name, value] of Object.entries(values)) {
      if (value) next.set(name, value)
      else next.delete(name)
    }
    if (!('page' in values)) next.delete('page')
    setParams(next)
  }

  async function saveColumns(selected: string[]) {
    if (!preferenceWorkspace) return setPreferences({ ...preferences, columns: selected })
    try {
      setPreferences(await preferenceClient.save(preferenceWorkspace, 'files', { columns: selected, page_size: pageSize }))
      setPreferenceError('')
    } catch { setPreferenceError(translate('collections.preferenceFailed')) }
  }

  async function resetPreferences() {
    try {
      setPreferences(preferenceWorkspace ? await preferenceClient.reset(preferenceWorkspace, 'files') : defaultPreferences(columns))
      const next = new URLSearchParams(params); next.delete('page'); next.delete('page_size'); setParams(next)
      setPreferenceError('')
    } catch { setPreferenceError(translate('collections.preferenceFailed')) }
  }

  const rows = (result?.results ?? []).map((file) => ({ ...file, name: file.filename }))
  const tableOrder = tableOrdering(query.ordering ?? '-created_at')
  return <>
    <header className="page-header"><div><h1>{translate('files.heading')}</h1><p>{translate('files.intro')}</p></div></header>
    {preferenceError && <p role="alert">{preferenceError}</p>}
    <section className="content-section" aria-labelledby="managed-files-heading">
      <div className="section-heading"><div><h2 id="managed-files-heading">{translate('files.managed')}</h2><p>{translate('files.scope')}</p></div></div>
      <div className="collection-toolbar">
        <form key={query.q} className="collection-search" onSubmit={(event) => { event.preventDefault(); const value = new FormData(event.currentTarget).get('q'); browse({ q: typeof value === 'string' ? value.trim() : '' }) }}><input name="q" type="search" defaultValue={query.q} aria-label={translate('files.search')} /><button type="submit" className="secondary-button">{translate('collections.searchAction')}</button></form>
        <FilterMenu groups={[{ kind: 'choices', label: translate('files.kind'), value: query.kind ?? '', choices: [{ value: '', label: translate('collections.all') }, { value: 'primary', label: translate('files.kind.primary') }, { value: 'attachment', label: translate('files.kind.attachment') }], onChange: (kind) => browse({ kind: kind || null }) }]} activeCount={Number(Boolean(query.kind))} onClear={() => browse({ kind: null })} />
        <ColumnChooser preferences={preferences} labels={labels} onSave={saveColumns} onReset={resetPreferences} />
        <label className="collection-page-size">{translate('collections.pageSize')}<select value={pageSize} onChange={(event) => { const size = Number(event.target.value) as 25 | 50 | 100; browse({ page_size: String(size) }); if (preferenceWorkspace) void preferenceClient.save(preferenceWorkspace, 'files', { columns: preferences.columns, page_size: size }).then(setPreferences).catch(() => setPreferenceError(translate('collections.preferenceFailed'))) }}>{[25, 50, 100].map((size) => <option key={size}>{size}</option>)}</select></label>
      </div>
      {query.kind && <div className="collection-active-filters"><button type="button" className="row-action" aria-label={translate('collections.removeFilter', { label: translate('files.kind') })} onClick={() => browse({ kind: null })}>{translate('files.kind')}: {translate(`files.kind.${query.kind}`)} ×</button></div>}
      <label className="collection-mobile-order">{translate('collections.ordering')}<select value={tableOrder} onChange={(event) => browse({ ordering: apiOrdering(event.target.value) })}>{columns.flatMap((column) => [<option key={column} value={column}>{labels[column]} ↑</option>, <option key={`-${column}`} value={`-${column}`}>{labels[column]} ↓</option>])}</select></label>
      {!response || response.key !== key ? <p role="status">{translate('files.loading')}</p> : !result ? <p role="alert">{translate('files.loadFailed')} <button type="button" onClick={() => setReload((value) => value + 1)}>{translate('collections.retry')}</button></p> : <>
        <p>{translate('files.count', { count: result.count })}</p>
        {rows.length === 0 ? <p className="empty-state">{query.q || query.kind ? translate('files.noMatches') : translate('files.empty')}</p> : <CollectionTable<DocumentFile & { name: string }> label={translate('files.table')} rows={rows} selectable={false} selected={new Set()} onSelection={() => {}} ordering={tableOrder} onOrder={(ordering) => browse({ ordering: apiOrdering(ordering) })} columns={preferences.columns.map((column) => ({ id: column, label: labels[column as keyof typeof labels], render: (file) => column === 'name' ? <><strong>{file.filename}</strong><span className="collection-secondary">{file.checksum.slice(0, 12)}</span><a className="secondary-button compact-button collection-file-download" href={client.attachmentDownloadUrl(scope, file.document_id, file.id)}><Download size={14} aria-hidden="true" />{translate('files.download')}</a></> : column === 'document' ? <Link to={documentPath(workspace, file.document_id)}>{file.document_title}</Link> : column === 'kind' ? `${translate(`files.kind.${file.kind}`)}${file.version ? ` · ${translate('files.version', { version: file.version })}` : ''}` : column === 'type' ? file.media_type : column === 'size' ? `${formatInteger(file.size)} B` : formatDateTime(file.created_at) }))} />}
        <CollectionPagination label={translate('files.table')} page={page} pageSize={pageSize} count={result.count} hasMore={result.has_more} onPageChange={(next) => browse({ page: String(next) })} />
      </>}
    </section>
  </>
}
