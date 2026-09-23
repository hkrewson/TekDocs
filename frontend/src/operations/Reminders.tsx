import { useCallback, useEffect, useMemo, useState } from 'react'
import { Download, Plus, Search } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { CollectionPagination } from '../CollectionPagination'
import { FilterMenu } from '../FilterMenu'
import { formatInteger, translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { EntityReference, RelationshipsClient } from '../relationships/api'
import type { WorkspaceContext } from '../workspaces/api'
import { browserOperationsClient } from './api'
import type { OperationsClient, ReminderInput, ReminderQuery, ReminderRecord, ReminderResult } from './api'

const emptyDraft: ReminderInput = { source_entity_id: '', domain: 'documentation', kind: 'review', title: '', due_on: '', lead_days: 30, recurrence: 'none' }
const domains: ReminderRecord['domain'][] = ['documentation', 'compliance', 'inventory', 'domain', 'invoice']
const orderings: ReminderQuery['ordering'][] = ['due_on', '-due_on', 'title', '-title']

function pageFrom(value: string | null) {
  const page = Number(value)
  return Number.isInteger(page) && page > 0 ? page : 1
}

function pageSizeFrom(value: string | null): ReminderQuery['page_size'] {
  const size = Number(value)
  return size === 50 || size === 100 ? size : 25
}

function domainFrom(value: string | null): ReminderQuery['domain'] {
  return domains.includes(value as ReminderRecord['domain']) ? value as ReminderRecord['domain'] : ''
}

function orderingFrom(value: string | null): ReminderQuery['ordering'] {
  return orderings.includes(value as ReminderQuery['ordering']) ? value as ReminderQuery['ordering'] : 'due_on'
}

function domainLabel(domain: ReminderRecord['domain']) {
  if (domain === 'domain') return translate('reminders.domains')
  if (domain === 'invoice') return translate('reminders.invoices')
  return translate(`reminders.${domain}`)
}

export function Reminders({ workspace, relationshipsClient, client = browserOperationsClient }: { workspace: WorkspaceContext | null; relationshipsClient: RelationshipsClient; client?: OperationsClient }) {
  const [parameters, setParameters] = useSearchParams()
  const scope = useMemo(() => workspace ? { organizationId: workspace.id } : {}, [workspace])
  const query = useMemo<ReminderQuery>(() => ({
    q: parameters.get('q') ?? '',
    domain: domainFrom(parameters.get('domain')),
    ordering: orderingFrom(parameters.get('ordering')),
    page: pageFrom(parameters.get('page')),
    page_size: pageSizeFrom(parameters.get('page_size')),
  }), [parameters])
  const creating = parameters.get('new') === '1'
  const [revision, setRevision] = useState(0)
  const queryKey = `${workspace?.id ?? 'msp'}\u0000${JSON.stringify(query)}\u0000${revision}`
  const [loaded, setLoaded] = useState<{ key: string; result: ReminderResult } | null>(null)
  const [failureKey, setFailureKey] = useState<string | null>(null)
  const [draft, setDraft] = useState<ReminderInput>(emptyDraft)
  const [sourceQuery, setSourceQuery] = useState('')
  const [sources, setSources] = useState<EntityReference[]>([])
  const [saving, setSaving] = useState(false)
  const [closingAfterSave, setClosingAfterSave] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [messageKind, setMessageKind] = useState<'success' | 'error'>('success')
  const result = loaded?.key === queryKey ? loaded.result : null
  const phase = failureKey === queryKey ? 'error' : result ? 'ready' : 'loading'
  const dirty = creating && !closingAfterSave && (JSON.stringify(draft) !== JSON.stringify(emptyDraft) || Boolean(sourceQuery))

  const resetDraft = useCallback(() => { setDraft(emptyDraft); setSourceQuery(''); setSources([]); setMessage(null) }, [])
  const attempt = useUnsavedChanges(dirty, saving && !closingAfterSave, resetDraft, creating && !closingAfterSave)

  const updateParameters = useCallback((changes: Record<string, string | number | null>, replace = false) => {
    const next = new URLSearchParams(parameters)
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === '' || value === 1 && key === 'page' || value === 25 && key === 'page_size' || value === 'due_on' && key === 'ordering') next.delete(key)
      else next.set(key, String(value))
    }
    setParameters(next, { replace })
  }, [parameters, setParameters])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      void client.reminderCollection(scope, query, controller.signal)
        .then((value) => { if (!controller.signal.aborted) { setLoaded({ key: queryKey, result: value }); setFailureKey(null) } })
        .catch(() => { if (!controller.signal.aborted) setFailureKey(queryKey) })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, query, queryKey, scope])

  useEffect(() => {
    if (!creating || sourceQuery.trim().length < 2 || draft.source_entity_id) {
      const clearTimer = window.setTimeout(() => setSources([]), 0)
      return () => window.clearTimeout(clearTimer)
    }
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      void relationshipsClient.search(scope, sourceQuery, undefined, controller.signal)
        .then((value) => setSources(value.results)).catch(() => setSources([]))
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [creating, draft.source_entity_id, relationshipsClient, scope, sourceQuery])

  const create = async () => {
    if (!draft.source_entity_id || !draft.title.trim() || !draft.due_on) return
    setSaving(true)
    setMessage(null)
    try {
      await client.createReminder(scope, { ...draft, title: draft.title.trim() })
      setClosingAfterSave(true)
      resetDraft()
      setMessage(translate('reminders.created'))
      setMessageKind('success')
      window.setTimeout(() => {
        updateParameters({ new: null, page: 1 })
        setClosingAfterSave(false)
      }, 50)
      setRevision((value) => value + 1)
    } catch {
      setMessage(translate('reminders.createFailed'))
      setMessageKind('error')
    } finally {
      setSaving(false)
    }
  }

  const closeCreate = () => attempt(() => {
    resetDraft()
    window.setTimeout(() => updateParameters({ new: null }), 0)
  })
  const activeFilters = [query.q ? translate('reminders.searchSummary', { query: query.q }) : '', query.domain ? domainLabel(query.domain) : ''].filter(Boolean)

  return <>
    <header className="page-header">
      <div><h1>{translate('reminders.heading')}</h1><p>{translate('reminders.intro')}</p></div>
      <div className="form-actions"><button className="primary-button" type="button" onClick={() => attempt(() => { setClosingAfterSave(false); updateParameters({ new: '1' }) })}><Plus size={16} />{translate('reminders.new')}</button><a className="secondary-button" href={client.reminderCalendarUrl(scope)}><Download size={16} />{translate('reminders.calendar')}</a></div>
    </header>
    {message && <div className={`form-message ${messageKind}`} role={messageKind === 'error' ? 'alert' : 'status'}>{message}</div>}
    {creating && <section className="content-section operations-create" aria-labelledby="new-reminder-heading">
      <div className="section-heading"><div><h2 id="new-reminder-heading">{translate('reminders.new')}</h2><p>{translate('reminders.newHelp')}</p></div></div>
      <div className="operations-form">
        <label>{translate('reminders.source')}<span className="search-input"><Search size={16} /><input autoFocus type="search" value={sourceQuery} onChange={(event) => { setSourceQuery(event.target.value); setDraft({ ...draft, source_entity_id: '' }) }} /></span></label>
        {sources.length > 0 && <ul className="operations-source-results">{sources.map((source) => <li key={source.id}><button type="button" onClick={() => { setDraft({ ...draft, source_entity_id: source.id }); setSourceQuery(source.display_name); setSources([]) }}>{source.display_name}<small>{source.entity_type.replaceAll('_', ' ')}</small></button></li>)}</ul>}
        <label>{translate('reminders.domain')}<select value={draft.domain} onChange={(event) => setDraft({ ...draft, domain: event.target.value as ReminderInput['domain'] })}><option value="documentation">{translate('reminders.documentation')}</option><option value="compliance">{translate('reminders.compliance')}</option><option value="inventory">{translate('reminders.inventory')}</option><option value="domain">{translate('reminders.domains')}</option></select></label>
        <label>{translate('reminders.title')}<input maxLength={240} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
        <label>{translate('reminders.due')}<input type="date" value={draft.due_on} onChange={(event) => setDraft({ ...draft, due_on: event.target.value })} /></label>
        <label>{translate('reminders.lead')}<input type="number" min={0} max={3650} value={draft.lead_days} onChange={(event) => setDraft({ ...draft, lead_days: Number(event.target.value) })} /></label>
        <label>{translate('reminders.recurrence')}<select value={draft.recurrence} onChange={(event) => setDraft({ ...draft, recurrence: event.target.value as ReminderInput['recurrence'] })}><option value="none">{translate('reminders.once')}</option><option value="annual">{translate('reminders.annual')}</option></select></label>
      </div>
      <div className="form-actions"><button className="primary-button" type="button" disabled={saving || !draft.source_entity_id || !draft.title.trim() || !draft.due_on} onClick={() => { void create() }}>{saving ? translate('common.saving') : translate('reminders.create')}</button><button className="secondary-button" type="button" disabled={saving} onClick={closeCreate}>{translate('common.cancel')}</button></div>
    </section>}
    <section className="content-section" aria-labelledby="reminder-agenda-heading">
      <div className="section-heading"><div><h2 id="reminder-agenda-heading">{translate('reminders.schedule')}</h2><p>{result ? translate('reminders.count', { count: formatInteger(result.count) }) : translate('common.loading')}</p></div></div>
      <div className="operations-filters">
        <label>{translate('reminders.search')}<span className="search-input"><Search size={16} /><input type="search" value={query.q} onChange={(event) => updateParameters({ q: event.target.value, page: 1 }, true)} /></span></label>
        <FilterMenu groups={[{ kind: 'choices', label: translate('reminders.domain'), value: query.domain, choices: [{ value: '', label: translate('reminders.allAreas') }, ...domains.map((value) => ({ value, label: domainLabel(value) }))], onChange: (value) => updateParameters({ domain: value, page: 1 }) }, { kind: 'choices', label: translate('reminders.order'), value: query.ordering, choices: [{ value: 'due_on', label: translate('reminders.dueSoonest') }, { value: '-due_on', label: translate('reminders.dueLatest') }, { value: 'title', label: translate('reminders.titleAscending') }, { value: '-title', label: translate('reminders.titleDescending') }], onChange: (value) => updateParameters({ ordering: value, page: 1 }) }]} activeCount={activeFilters.length + (query.ordering === 'due_on' ? 0 : 1)} onClear={() => updateParameters({ q: null, domain: null, ordering: null, page: 1 })} menuLabel={translate('reminders.filters')} />
      </div>
      {activeFilters.length > 0 && <div className="form-actions">{activeFilters.map((value) => <span key={value}>{value}</span>)}<button type="button" className="row-action" onClick={() => updateParameters({ q: null, domain: null, page: 1 })}>{translate('collections.clearFilters')}</button></div>}
      {phase === 'loading' && <p role="status">{translate('reminders.loading')}</p>}
      {phase === 'error' && <div role="alert"><p>{translate('reminders.loadFailed')}</p><button className="secondary-button" type="button" onClick={() => setRevision((value) => value + 1)}>{translate('notifications.tryAgain')}</button></div>}
      {phase === 'ready' && result?.results.length === 0 && <p className="empty-state">{activeFilters.length ? translate('reminders.noMatches') : translate('reminders.empty')}</p>}
      {phase === 'ready' && result && result.results.length > 0 && <ol className="plain-detail-list">{result.results.map((record) => <li key={record.id}><div><strong>{record.title}</strong><span>{record.source} · {domainLabel(record.domain)} · {record.owner ?? translate('reminders.unassigned')}</span></div><div><time dateTime={record.due_on}>{new Date(`${record.due_on}T00:00:00`).toLocaleDateString()}</time><span>{record.recurrence === 'annual' ? translate('reminders.annual') : translate('reminders.once')}</span></div></li>)}</ol>}
      {result && <CollectionPagination label={translate('reminders.schedule')} page={query.page} pageSize={query.page_size} count={result.count} hasMore={result.has_more} onPageChange={(page) => updateParameters({ page })} />}
      <label>{translate('collections.pageSize')}<select value={query.page_size} onChange={(event) => updateParameters({ page_size: Number(event.target.value), page: 1 })}><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option></select></label>
    </section>
  </>
}
