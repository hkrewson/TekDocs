import { useEffect, useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { CollectionPagination } from '../CollectionPagination'
import { FilterMenu } from '../FilterMenu'
import { formatInteger, translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import { browserOperationsClient } from './api'
import type { ActivityResult, OperationsClient } from './api'

function positiveNumber(value: string | null, fallback: number) {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback
}

function pageSize(value: string | null) {
  const parsed = positiveNumber(value, 25)
  return parsed === 50 || parsed === 100 ? parsed : 25
}

export function ActivityLog({ workspace, client = browserOperationsClient }: { workspace: WorkspaceContext | null; client?: OperationsClient }) {
  const scope = useMemo(() => workspace ? { organizationId: workspace.id } : {}, [workspace])
  const [parameters, setParameters] = useSearchParams()
  const filters = useMemo(() => ({
    q: parameters.get('q') ?? '',
    occurred_after: parameters.get('after') ?? '',
    occurred_before: parameters.get('before') ?? '',
    page: positiveNumber(parameters.get('page'), 1),
    page_size: pageSize(parameters.get('page_size')),
  }), [parameters])
  const [revision, setRevision] = useState(0)
  const queryKey = `${workspace?.id ?? 'msp'}\u0000${JSON.stringify(filters)}\u0000${revision}`
  const [loaded, setLoaded] = useState<{ key: string; result: ActivityResult } | null>(null)
  const [failureKey, setFailureKey] = useState<string | null>(null)
  const result = loaded?.key === queryKey ? loaded.result : null
  const phase = failureKey === queryKey ? 'error' : result ? 'ready' : 'loading'

  function update(changes: Record<string, string | number | null>, replace = false) {
    const next = new URLSearchParams(parameters)
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === '' || value === 1 && key === 'page' || value === 25 && key === 'page_size') next.delete(key)
      else next.set(key, String(value))
    }
    setParameters(next, { replace })
  }

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      void client.activity(scope, filters, controller.signal)
        .then((value) => { if (!controller.signal.aborted) { setLoaded({ key: queryKey, result: value }); setFailureKey(null) } })
        .catch(() => { if (!controller.signal.aborted) setFailureKey(queryKey) })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, filters, queryKey, scope])

  const activeDateFilterCount = [filters.occurred_after, filters.occurred_before].filter(Boolean).length
  const dateFilterLabel = filters.occurred_after && filters.occurred_before
    ? translate('activity.customRange')
    : filters.occurred_after
      ? translate('activity.afterDate')
      : filters.occurred_before
        ? translate('activity.beforeDate')
        : translate('activity.anyTime')
  const activeFilters = [filters.q ? translate('activity.searchSummary', { query: filters.q }) : '', activeDateFilterCount ? dateFilterLabel : ''].filter(Boolean)

  return <>
    <header className="page-header"><div><h1>{translate('activity.heading')}</h1><p>{translate('activity.intro')}</p></div></header>
    <section className="content-section" aria-labelledby="activity-stream-heading">
      <div className="section-heading"><div><h2 id="activity-stream-heading">{translate('activity.stream')}</h2><p>{result ? translate('activity.count', { count: formatInteger(result.count) }) : translate('common.loading')}</p></div></div>
      <div className="operations-filters">
        <label>{translate('activity.search')}<span className="search-input"><Search size={16} /><input type="search" value={filters.q} onChange={(event) => update({ q: event.target.value, page: 1 }, true)} /></span></label>
        <FilterMenu groups={[{
          kind: 'custom',
          label: translate('activity.dateRange'),
          valueLabel: dateFilterLabel,
          content: <div className="filter-menu-custom"><label>{translate('activity.after')}<input type="datetime-local" value={filters.occurred_after} onChange={(event) => update({ after: event.target.value, page: 1 })} /></label><label>{translate('activity.before')}<input type="datetime-local" value={filters.occurred_before} onChange={(event) => update({ before: event.target.value, page: 1 })} /></label></div>,
        }]} activeCount={activeDateFilterCount} onClear={() => update({ after: null, before: null, page: 1 })} menuLabel={translate('activity.filters')} />
      </div>
      {activeFilters.length > 0 && <div className="form-actions">{activeFilters.map((value) => <span key={value}>{value}</span>)}<button type="button" className="row-action" onClick={() => update({ q: null, after: null, before: null, page: 1 })}>{translate('collections.clearFilters')}</button></div>}
      {phase === 'loading' && <p role="status">{translate('activity.loading')}</p>}
      {phase === 'error' && <div role="alert"><p>{translate('activity.loadFailed')}</p><button className="secondary-button" type="button" onClick={() => setRevision((value) => value + 1)}>{translate('notifications.tryAgain')}</button></div>}
      {phase === 'ready' && result?.results.length === 0 && <p className="empty-state">{translate('activity.empty')}</p>}
      {phase === 'ready' && result && result.results.length > 0 && <ol className="plain-detail-list">{result.results.map((record) => <li key={record.id}><div><strong>{record.action.replaceAll('.', ' ')}</strong><span>{record.entity_name ?? '—'}{record.entity_type ? ` · ${record.entity_type.replaceAll('_', ' ')}` : ''}</span></div><div><time dateTime={record.occurred_at}>{new Date(record.occurred_at).toLocaleString()}</time><span>{record.actor_name ?? translate('activity.system')}</span>{record.request_id && <span title={record.request_id}>{translate('activity.requestShort', { request: `${record.request_id.slice(0, 8)}…` })}</span>}</div></li>)}</ol>}
      {result && <CollectionPagination label={translate('activity.table')} page={filters.page} pageSize={filters.page_size} count={result.count} hasMore={result.has_more} onPageChange={(page) => update({ page })} />}
      <label>{translate('collections.pageSize')}<select value={filters.page_size} onChange={(event) => update({ page_size: Number(event.target.value), page: 1 })}><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option></select></label>
    </section>
  </>
}
