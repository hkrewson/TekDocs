import { useEffect, useMemo, useState } from 'react'
import { RotateCcw, Search } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { CollectionPagination } from '../CollectionPagination'
import { FilterMenu } from '../FilterMenu'
import { formatDateTime, translate } from '../i18n/localization'
import type { MessageId } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import { browserRecycleBinClient } from './api'
import type { RecycleBinClient, RecycleBinItem, RecycleBinQuery, RecycleBinRecordType, RecycleBinResult } from './api'

const typeLabelKeys: Record<RecycleBinRecordType, MessageId> = {
  organization: 'recycleBin.type.organization',
  person_association: 'recycleBin.type.person',
  site: 'recycleBin.type.site',
  location: 'recycleBin.type.location',
  custom_field_definition: 'recycleBin.type.customField',
  commercial_contract: 'recycleBin.type.contract',
}

function pageFrom(value: string | null) {
  const page = Number(value)
  return Number.isInteger(page) && page > 0 ? page : 1
}

function pageSizeFrom(value: string | null): RecycleBinQuery['pageSize'] {
  const pageSize = Number(value)
  return pageSize === 50 || pageSize === 100 ? pageSize : 25
}

function recordTypeFrom(value: string | null): RecycleBinRecordType | '' {
  return value && value in typeLabelKeys ? value as RecycleBinRecordType : ''
}

export function RecycleBin({ workspace, client = browserRecycleBinClient }: { workspace: WorkspaceContext | null; client?: RecycleBinClient }) {
  const [parameters, setParameters] = useSearchParams()
  const scope = useMemo(() => ({ organizationId: workspace?.id }), [workspace?.id])
  const query = parameters.get('q') ?? ''
  const recordType = recordTypeFrom(parameters.get('record_type'))
  const page = pageFrom(parameters.get('page'))
  const pageSize = pageSizeFrom(parameters.get('page_size')) ?? 25
  const [revision, setRevision] = useState(0)
  const key = `${workspace?.id ?? 'msp'}\u0000${query}\u0000${recordType}\u0000${page}\u0000${pageSize}\u0000${revision}`
  const [loaded, setLoaded] = useState<{ key: string; result: RecycleBinResult } | null>(null)
  const [failureKey, setFailureKey] = useState<string | null>(null)
  const [selected, setSelected] = useState<RecycleBinItem | null>(null)
  const [restoring, setRestoring] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const result = loaded?.key === key ? loaded.result : null
  const phase = failureKey === key ? 'error' : result ? 'ready' : 'loading'

  function updateParameters(changes: Record<string, string | number | null>, replace = false) {
    const next = new URLSearchParams(parameters)
    for (const [name, value] of Object.entries(changes)) {
      if (value === null || value === '' || name === 'page' && value === 1 || name === 'page_size' && value === 25) next.delete(name)
      else next.set(name, String(value))
    }
    setParameters(next, { replace })
  }

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      void client.list(scope, { query, recordType, page, pageSize }, controller.signal)
        .then((value) => { if (!controller.signal.aborted) { setLoaded({ key, result: value }); setFailureKey(null) } })
        .catch(() => { if (!controller.signal.aborted) setFailureKey(key) })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, key, page, pageSize, query, recordType, scope])

  const restore = async () => {
    if (!selected) return
    setRestoring(true); setRestoreError(null); setNotice(null)
    try {
      await client.restore(scope, selected)
      setSelected(null)
      setNotice(translate('recycleBin.restored', { name: selected.label }))
      setRevision((value) => value + 1)
    } catch {
      setRestoreError(translate('recycleBin.restoreFailed'))
    } finally {
      setRestoring(false)
    }
  }

  return <>
    <header className="page-header"><div><h1>{translate('recycleBin.heading')}</h1><p>{translate('recycleBin.intro', { workspace: workspace?.name ?? translate('recycleBin.mspWorkspace') })}</p></div></header>
    {restoreError && <div className="form-message error" role="alert">{restoreError}</div>}
    {notice && <div className="form-message success" role="status">{notice}</div>}
    <section className="content-section" aria-labelledby="recycle-bin-heading">
      <div className="section-heading recycle-bin-heading"><h2 id="recycle-bin-heading">{translate('recycleBin.archivedRecords')}</h2><span>{result ? translate('recycleBin.count', { count: result.count }) : translate('common.loading')}</span></div>
      <div className="recycle-bin-toolbar">
        <label className="recycle-bin-search"><Search size={16} aria-hidden="true" /><span className="sr-only">{translate('recycleBin.search')}</span><input type="search" value={query} onChange={(event) => updateParameters({ q: event.target.value, page: 1 }, true)} placeholder={translate('recycleBin.search')} /></label>
        <FilterMenu groups={[{ kind: 'choices', label: translate('recycleBin.recordType'), value: recordType, choices: [{ value: '', label: translate('recycleBin.allTypes') }, ...Object.entries(typeLabelKeys).map(([value, labelKey]) => ({ value, label: translate(labelKey) }))], onChange: (value) => updateParameters({ record_type: value, page: 1 }) }]} activeCount={recordType ? 1 : 0} onClear={() => updateParameters({ record_type: null, page: 1 })} menuLabel={translate('recycleBin.filters')} />
        <label className="collection-page-size">{translate('collections.pageSize')}<select value={pageSize} onChange={(event) => updateParameters({ page_size: Number(event.target.value), page: 1 })}><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option></select></label>
      </div>
      {(query || recordType) && <div className="collection-active-filters">{query && <button type="button" className="row-action" onClick={() => updateParameters({ q: null, page: 1 })}>{translate('recycleBin.searchSummary', { query })} ×</button>}{recordType && <button type="button" className="row-action" onClick={() => updateParameters({ record_type: null, page: 1 })}>{translate(typeLabelKeys[recordType])} ×</button>}</div>}
      {phase === 'loading' && <p className="empty-state" role="status">{translate('recycleBin.loading')}</p>}
      {phase === 'error' && <div className="empty-state" role="alert"><p>{translate('recycleBin.unavailable')}</p><button className="secondary-button" type="button" onClick={() => setRevision((value) => value + 1)}>{translate('common.retry')}</button></div>}
      {phase === 'ready' && result?.results.length === 0 && <p className="empty-state">{query || recordType ? translate('recycleBin.noMatches') : translate('recycleBin.empty')}</p>}
      {phase === 'ready' && result && result.results.length > 0 && <>
        <ol className="plain-detail-list recovery-list">{result.results.map((item) => <li key={`${item.record_type}:${item.id}`}><div><strong>{item.label}</strong><span>{translate(typeLabelKeys[item.record_type])} · {formatDateTime(item.archived_at)}</span><span>{translate('recycleBin.affectedSummary', { count: item.cascade_count })}</span></div><button className="row-action" type="button" disabled={!item.can_restore} title={item.can_restore ? undefined : translate('recycleBin.noPermission')} onClick={() => { setSelected(item); setNotice(null); setRestoreError(null) }}><RotateCcw size={15} aria-hidden="true" />{translate('common.restore')}</button></li>)}</ol>
        <CollectionPagination label={translate('recycleBin.archivedRecords')} page={page} pageSize={pageSize} count={result.count} hasMore={result.has_more} onPageChange={(nextPage) => updateParameters({ page: nextPage })} />
      </>}
      {selected && <div className="archive-confirmation" role="alertdialog" aria-labelledby="restore-record-heading"><div><strong id="restore-record-heading">{translate('recycleBin.restoreHeading', { name: selected.label })}</strong><p>{selected.cascade_count > 1 ? translate('recycleBin.restoreRelated', { count: selected.cascade_count - 1, records: selected.cascade_count === 2 ? translate('recycleBin.record') : translate('recycleBin.records') }) : translate('recycleBin.restoreOne')}</p></div><div className="form-actions"><button className="primary-button" type="button" disabled={restoring} onClick={() => { void restore() }}>{restoring ? translate('recycleBin.restoring') : translate('common.restore')}</button><button className="secondary-button" type="button" disabled={restoring} onClick={() => setSelected(null)}>{translate('common.cancel')}</button></div></div>}
    </section>
  </>
}
