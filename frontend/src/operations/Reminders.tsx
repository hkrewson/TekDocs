import { useCallback, useEffect, useMemo, useState } from 'react'
import { CalendarDays, Download, Plus, Search } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { EntityReference, RelationshipsClient } from '../relationships/api'
import type { WorkspaceContext } from '../workspaces/api'
import { browserOperationsClient } from './api'
import type { OperationsClient, ReminderInput, ReminderRecord } from './api'

const emptyDraft: ReminderInput = { source_entity_id: '', domain: 'documentation', kind: 'review', title: '', due_on: '', lead_days: 30, recurrence: 'none' }

export function Reminders({ workspace, relationshipsClient, client = browserOperationsClient }: { workspace: WorkspaceContext | null; relationshipsClient: RelationshipsClient; client?: OperationsClient }) {
  const scope = useMemo(() => workspace ? { organizationId: workspace.id } : {}, [workspace])
  const [records, setRecords] = useState<ReminderRecord[]>([])
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [draft, setDraft] = useState<ReminderInput>(emptyDraft)
  const [sourceQuery, setSourceQuery] = useState('')
  const [sources, setSources] = useState<EntityReference[]>([])
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = useCallback(() => {
    client.reminders(scope).then((result) => { setRecords(result); setPhase('ready') }).catch(() => setPhase('error'))
  }, [client, scope])

  useEffect(load, [load])
  useEffect(() => {
    if (sourceQuery.trim().length < 2) {
      const clearTimer = window.setTimeout(() => setSources([]), 0)
      return () => window.clearTimeout(clearTimer)
    }
    const controller = new AbortController()
    const timer = window.setTimeout(() => relationshipsClient.search(scope, sourceQuery, undefined, controller.signal)
      .then((result) => setSources(result.results)).catch(() => setSources([])), 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [relationshipsClient, scope, sourceQuery])

  const create = async () => {
    if (!draft.source_entity_id || !draft.title.trim() || !draft.due_on) return
    setSaving(true)
    setMessage(null)
    try {
      await client.createReminder(scope, { ...draft, title: draft.title.trim() })
      setDraft(emptyDraft)
      setSourceQuery('')
      setSources([])
      setMessage(translate('reminders.created'))
      load()
    } catch {
      setMessage(translate('reminders.createFailed'))
    } finally {
      setSaving(false)
    }
  }

  return <>
    <header className="page-header">
      <div><h1>{translate('reminders.heading')}</h1><p>{translate('reminders.intro')}</p></div>
      <a className="secondary-button" href={client.reminderCalendarUrl(scope)}><Download size={16} />{translate('reminders.calendar')}</a>
    </header>
    {message && <div className="form-message" role="status">{message}</div>}
    <section className="content-section operations-create" aria-labelledby="new-reminder-heading">
      <div className="section-heading"><h2 id="new-reminder-heading">{translate('reminders.new')}</h2></div>
      <div className="operations-form">
        <label>{translate('reminders.source')}<span className="search-input"><Search size={16} /><input type="search" value={sourceQuery} onChange={(event) => { setSourceQuery(event.target.value); setDraft({ ...draft, source_entity_id: '' }) }} /></span></label>
        {sources.length > 0 && <ul className="operations-source-results">{sources.map((source) => <li key={source.id}><button type="button" onClick={() => { setDraft({ ...draft, source_entity_id: source.id }); setSourceQuery(source.display_name); setSources([]) }}>{source.display_name}<small>{source.entity_type.replaceAll('_', ' ')}</small></button></li>)}</ul>}
        <label>{translate('reminders.domain')}<select value={draft.domain} onChange={(event) => setDraft({ ...draft, domain: event.target.value as ReminderInput['domain'] })}><option value="documentation">{translate('reminders.documentation')}</option><option value="compliance">{translate('reminders.compliance')}</option><option value="inventory">{translate('reminders.inventory')}</option><option value="domain">{translate('reminders.domains')}</option></select></label>
        <label>{translate('reminders.title')}<input maxLength={240} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
        <label>{translate('reminders.due')}<input type="date" value={draft.due_on} onChange={(event) => setDraft({ ...draft, due_on: event.target.value })} /></label>
        <label>{translate('reminders.lead')}<input type="number" min={0} max={3650} value={draft.lead_days} onChange={(event) => setDraft({ ...draft, lead_days: Number(event.target.value) })} /></label>
        <label>{translate('reminders.recurrence')}<select value={draft.recurrence} onChange={(event) => setDraft({ ...draft, recurrence: event.target.value as ReminderInput['recurrence'] })}><option value="none">{translate('reminders.once')}</option><option value="annual">{translate('reminders.annual')}</option></select></label>
      </div>
      <button className="primary-button" type="button" disabled={saving || !draft.source_entity_id || !draft.title.trim() || !draft.due_on} onClick={() => { void create() }}><Plus size={16} />{translate('reminders.create')}</button>
    </section>
    <section className="content-section">
      <div className="section-heading"><h2>{translate('reminders.schedule')}</h2><span>{records.length}</span></div>
      {phase === 'loading' && <p role="status">{translate('reminders.loading')}</p>}
      {phase === 'error' && <p role="alert">{translate('reminders.loadFailed')}</p>}
      {phase === 'ready' && records.length === 0 && <p className="empty-state">{translate('reminders.empty')}</p>}
      {phase === 'ready' && records.length > 0 && <div className="table-scroll" tabIndex={0} role="group" aria-label={translate('reminders.table')}>
        <table className="data-table">
          <caption>{translate('reminders.table')}</caption>
          <thead><tr><th>{translate('reminders.title')}</th><th>{translate('reminders.source')}</th><th>{translate('reminders.due')}</th><th>{translate('reminders.owner')}</th><th>{translate('reminders.recurrence')}</th></tr></thead>
          <tbody>{records.map((record) => <tr key={record.id}><th scope="row"><CalendarDays size={15} /> {record.title}</th><td>{record.source}</td><td>{new Date(`${record.due_on}T00:00:00`).toLocaleDateString()}</td><td>{record.owner ?? '—'}</td><td>{record.recurrence === 'annual' ? translate('reminders.annual') : translate('reminders.once')}</td></tr>)}</tbody>
        </table>
      </div>}
    </section>
  </>
}
