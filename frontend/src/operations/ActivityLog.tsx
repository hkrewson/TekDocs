import { useEffect, useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { FilterMenu } from '../FilterMenu'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import { browserOperationsClient } from './api'
import type { ActivityResult, OperationsClient } from './api'

export function ActivityLog({ workspace, client = browserOperationsClient }: { workspace: WorkspaceContext | null; client?: OperationsClient }) {
  const scope = useMemo(() => workspace ? { organizationId: workspace.id } : {}, [workspace])
  const [filters, setFilters] = useState({ q: '', occurred_after: '', occurred_before: '', page: 1 })
  const [result, setResult] = useState<ActivityResult | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => client.activity(scope, filters, controller.signal)
      .then((value) => { setResult(value); setPhase('ready') })
      .catch(() => setPhase('error')), 150)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, filters, scope])

  const activeDateFilterCount = [filters.occurred_after, filters.occurred_before].filter(Boolean).length
  const dateFilterLabel = filters.occurred_after && filters.occurred_before
    ? 'Custom range'
    : filters.occurred_after
      ? 'After a date'
      : filters.occurred_before
        ? 'Before a date'
        : 'Any time'

  return <>
    <header className="page-header">
      <div><h1>{translate('activity.heading')}</h1><p>{translate('activity.intro')}</p></div>
    </header>
    <section className="content-section">
      <div className="operations-filters">
        <label>{translate('activity.search')}<span className="search-input"><Search size={16} /><input type="search" value={filters.q} onChange={(event) => setFilters({ ...filters, q: event.target.value, page: 1 })} /></span></label>
        <FilterMenu groups={[{
          kind: 'custom',
          label: 'Date range',
          valueLabel: dateFilterLabel,
          content: <div className="filter-menu-custom"><label>{translate('activity.after')}<input type="datetime-local" value={filters.occurred_after} onChange={(event) => setFilters({ ...filters, occurred_after: event.target.value, page: 1 })} /></label><label>{translate('activity.before')}<input type="datetime-local" value={filters.occurred_before} onChange={(event) => setFilters({ ...filters, occurred_before: event.target.value, page: 1 })} /></label></div>,
        }]} activeCount={activeDateFilterCount} onClear={() => setFilters({ ...filters, occurred_after: '', occurred_before: '', page: 1 })} menuLabel="Activity filters" />
      </div>
      {phase === 'loading' && <p role="status">{translate('activity.loading')}</p>}
      {phase === 'error' && <p role="alert">{translate('activity.loadFailed')}</p>}
      {phase === 'ready' && result?.results.length === 0 && <p className="empty-state">{translate('activity.empty')}</p>}
      {phase === 'ready' && result && result.results.length > 0 && <div className="table-scroll" tabIndex={0} role="group" aria-label={translate('activity.table')}>
        <table className="data-table">
          <caption>{translate('activity.table')}</caption>
          <thead><tr><th>{translate('activity.time')}</th><th>{translate('activity.action')}</th><th>{translate('activity.actor')}</th><th>{translate('activity.record')}</th><th>{translate('activity.request')}</th></tr></thead>
          <tbody>{result.results.map((record) => <tr key={record.id}><td>{new Date(record.occurred_at).toLocaleString()}</td><th scope="row">{record.action.replaceAll('.', ' ')}</th><td>{record.actor_name ?? translate('activity.system')}</td><td>{record.entity_name ?? '—'}{record.entity_type ? <small>{record.entity_type.replaceAll('_', ' ')}</small> : null}</td><td><code>{record.request_id ?? '—'}</code></td></tr>)}</tbody>
        </table>
      </div>}
      {result && <nav className="history-pagination" aria-label={translate('activity.pages')}>
        <button className="secondary-button" type="button" disabled={filters.page === 1} onClick={() => setFilters({ ...filters, page: filters.page - 1 })}>{translate('pagination.previous')}</button>
        <span>{translate('pagination.page', { page: filters.page })}</span>
        <button className="secondary-button" type="button" disabled={!result.has_more} onClick={() => setFilters({ ...filters, page: filters.page + 1 })}>{translate('pagination.next')}</button>
      </nav>}
    </section>
  </>
}
