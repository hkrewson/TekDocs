import { useEffect, useMemo, useState } from 'react'
import { RotateCcw, Search } from 'lucide-react'
import { formatDateTime } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import { browserRecycleBinClient } from './api'
import type { RecycleBinClient, RecycleBinItem, RecycleBinRecordType } from './api'

const typeLabels: Record<RecycleBinRecordType, string> = {
  organization: 'Organization',
  person_association: 'Person',
  site: 'Site',
  location: 'Location',
  custom_field_definition: 'Custom field',
  commercial_contract: 'Commercial contract',
}

function messageFor(error: unknown) {
  return error instanceof Error ? error.message : 'The recycle bin could not be loaded.'
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
        .catch((loadError: unknown) => {
          if (controller.signal.aborted) return
          setPhase('error')
          setError(messageFor(loadError))
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
      setNotice(`${selected.label} restored.`)
      setRevision((value) => value + 1)
    } catch (restoreError) {
      setError(messageFor(restoreError))
    } finally {
      setRestoring(false)
    }
  }

  return (
    <>
      <header className="page-header"><div><h1>Recycle bin</h1><p>Recover archived records from {workspace?.name ?? 'the MSP workspace'}. Restores are permission-checked and audited.</p></div></header>
      {error && <div className="form-message error" role="alert">{error}</div>}
      {notice && <div className="form-message success" role="status">{notice}</div>}
      <section className="content-section" aria-labelledby="recycle-bin-heading">
        <div className="section-heading recycle-bin-heading"><h2 id="recycle-bin-heading">Archived records</h2><span>{items ? `${items.length} shown` : 'Loading'}</span></div>
        <div className="recycle-bin-toolbar">
          <label className="recycle-bin-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search archived records</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search archived records" /></label>
          <label><span>Record type</span><select value={recordType} onChange={(event) => setRecordType(event.target.value as RecycleBinRecordType | '')}><option value="">All types</option>{Object.entries(typeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        </div>
        {visiblePhase === 'loading' && <p className="empty-state" role="status">Loading archived records…</p>}
        {visiblePhase === 'error' && <p className="empty-state">Archived records are unavailable.</p>}
        {visiblePhase === 'ready' && items?.length === 0 && <p className="empty-state">{query || recordType ? 'No archived records match these filters.' : 'This workspace has no recoverable archived records.'}</p>}
        {visiblePhase === 'ready' && items && items.length > 0 && <div className="recycle-bin-table-wrap"><table className="recycle-bin-table"><thead><tr><th>Name</th><th>Type</th><th>Archived</th><th>Affected records</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{items.map((item) => <tr key={`${item.record_type}:${item.id}`}><td><strong>{item.label}</strong></td><td>{typeLabels[item.record_type]}</td><td>{archivedDate(item.archived_at)}</td><td>{item.cascade_count}</td><td><button className="row-action" type="button" disabled={!item.can_restore} title={item.can_restore ? undefined : 'You do not have permission to restore this record'} onClick={() => { setSelected(item); setNotice(null) }}><RotateCcw size={15} />Restore</button></td></tr>)}</tbody></table></div>}
        {selected && <div className="archive-confirmation" role="alertdialog" aria-labelledby="restore-record-heading"><div><strong id="restore-record-heading">Restore {selected.label}?</strong><p>{selected.cascade_count > 1 ? `This also restores ${selected.cascade_count - 1} record${selected.cascade_count === 2 ? '' : 's'} archived in the same cascade.` : 'The record will return to this workspace.'}</p></div><div className="form-actions"><button className="primary-button" type="button" disabled={restoring} onClick={() => { void restore() }}>{restoring ? 'Restoring…' : 'Restore'}</button><button className="secondary-button" type="button" disabled={restoring} onClick={() => setSelected(null)}>Cancel</button></div></div>}
      </section>
    </>
  )
}
