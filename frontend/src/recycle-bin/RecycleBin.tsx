import { useEffect, useMemo, useState } from 'react'
import { RotateCcw, Search } from 'lucide-react'
import { FilterMenu } from '../FilterMenu'
import { formatDateTime, translate} from '../i18n/localization'
import type { MessageId } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import { browserRecycleBinClient } from './api'
import type { RecycleBinClient, RecycleBinItem, RecycleBinRecordType } from './api'

const typeLabelKeys: Record<RecycleBinRecordType, MessageId> = {
  organization: 'recycleBin.type.organization',
  person_association: 'recycleBin.type.person',
  site: 'recycleBin.type.site',
  location: 'recycleBin.type.location',
  custom_field_definition: 'recycleBin.type.customField',
  commercial_contract: 'recycleBin.type.contract',
}

function archivedDate(value: string) {
  return formatDateTime(value)
}

export function RecycleBin({ workspace, client = browserRecycleBinClient }: { workspace: WorkspaceContext | null; client?: RecycleBinClient }) {
  const scope = useMemo(() => ({ organizationId: workspace?.id }), [workspace?.id])
  const scopeKey = workspace?.id ?? 'msp'
  const [query, setQuery] = useState('')
  const [recordType, setRecordType] = useState<RecycleBinRecordType | ''>('')
  const [loaded, setLoaded] = useState<{ scopeKey: string; items: RecycleBinItem[] } | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [selected, setSelected] = useState<RecycleBinItem | null>(null)
  const [restoring, setRestoring] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.list(scope, { query, recordType }, controller.signal)
        .then((result) => {
          if (controller.signal.aborted) return
          setLoaded({ scopeKey, items: result.results })
          setPhase('ready')
          setError(null)
        })
        .catch(() => {
          if (controller.signal.aborted) return
          setPhase('error')
          setError(translate('recycleBin.loadFailed'))
        })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, query, recordType, revision, scope, scopeKey])

  const items = loaded?.scopeKey === scopeKey ? loaded.items : null
  const visiblePhase = loaded && loaded.scopeKey !== scopeKey ? 'loading' : phase
  const restore = async () => {
    if (!selected) return
    setRestoring(true); setError(null); setNotice(null)
    try {
      await client.restore(scope, selected)
      setSelected(null)
      setNotice(translate('recycleBin.restored', { name: selected.label }))
      setRevision((value) => value + 1)
    } catch {
      setError(translate('recycleBin.restoreFailed'))
    } finally {
      setRestoring(false)
    }
  }

  return (
    <>
      <header className="page-header"><div><h1>{translate('recycleBin.heading')}</h1><p>{translate('recycleBin.intro', { workspace: workspace?.name ?? translate('recycleBin.mspWorkspace') })}</p></div></header>
      {error && <div className="form-message error" role="alert">{error}</div>}
      {notice && <div className="form-message success" role="status">{notice}</div>}
      <section className="content-section" aria-labelledby="recycle-bin-heading">
        <div className="section-heading recycle-bin-heading"><h2 id="recycle-bin-heading">{translate('recycleBin.archivedRecords')}</h2><span>{items ? translate('recycleBin.shown', { count: items.length }) : translate('common.loading')}</span></div>
        <div className="recycle-bin-toolbar">
          <label className="recycle-bin-search"><Search size={16} aria-hidden="true" /><span className="sr-only">{translate('recycleBin.search')}</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={translate('recycleBin.search')} /></label>
          <FilterMenu groups={[{ kind: 'choices', label: translate('recycleBin.recordType'), value: recordType, choices: [{ value: '', label: translate('recycleBin.allTypes') }, ...Object.entries(typeLabelKeys).map(([value, labelKey]) => ({ value, label: translate(labelKey) }))], onChange: (value) => setRecordType(value as RecycleBinRecordType | '') }]} activeCount={recordType ? 1 : 0} onClear={() => setRecordType('')} menuLabel={translate('recycleBin.filters')} />
        </div>
        {visiblePhase === 'loading' && <p className="empty-state" role="status">{translate('recycleBin.loading')}</p>}
        {visiblePhase === 'error' && <p className="empty-state">{translate('recycleBin.unavailable')}</p>}
        {visiblePhase === 'ready' && items?.length === 0 && <p className="empty-state">{query || recordType ? translate('recycleBin.noMatches') : translate('recycleBin.empty')}</p>}
        {visiblePhase === 'ready' && items && items.length > 0 && <div className="recycle-bin-table-wrap" role="group" aria-label={translate('recycleBin.table')} tabIndex={0}><table className="recycle-bin-table"><thead><tr><th>{translate('recycleBin.name')}</th><th>{translate('recycleBin.recordType')}</th><th>{translate('recycleBin.archived')}</th><th>{translate('recycleBin.affected')}</th><th><span className="sr-only">{translate('common.actions')}</span></th></tr></thead><tbody>{items.map((item) => <tr key={`${item.record_type}:${item.id}`}><td><strong>{item.label}</strong></td><td>{translate(typeLabelKeys[item.record_type])}</td><td>{archivedDate(item.archived_at)}</td><td>{item.cascade_count}</td><td><button className="row-action" type="button" disabled={!item.can_restore} title={item.can_restore ? undefined : translate('recycleBin.noPermission')} onClick={() => { setSelected(item); setNotice(null) }}><RotateCcw size={15} />{translate('common.restore')}</button></td></tr>)}</tbody></table></div>}
        {selected && <div className="archive-confirmation" role="alertdialog" aria-labelledby="restore-record-heading"><div><strong id="restore-record-heading">{translate('recycleBin.restoreHeading', { name: selected.label })}</strong><p>{selected.cascade_count > 1 ? translate('recycleBin.restoreRelated', { count: selected.cascade_count - 1, records: selected.cascade_count === 2 ? translate('recycleBin.record') : translate('recycleBin.records') }) : translate('recycleBin.restoreOne')}</p></div><div className="form-actions"><button className="primary-button" type="button" disabled={restoring} onClick={() => { void restore() }}>{restoring ? translate('recycleBin.restoring') : translate('common.restore')}</button><button className="secondary-button" type="button" disabled={restoring} onClick={() => setSelected(null)}>{translate('common.cancel')}</button></div></div>}
      </section>
    </>
  )
}
