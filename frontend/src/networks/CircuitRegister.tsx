import { useMemo, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router'
import { browserCollectionPreferences } from '../collections/preferences'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import { RecordActivity } from '../records/RecordActivity'
import { RecordHeader, RecordSections } from '../records/RecordNavigation'
import type { WorkspaceContext } from '../workspaces/api'
import { HandoffView } from './HandoffView'
import { CircuitEditor } from './CircuitEditor'
import { NetworkChildCollection } from './NetworkChildCollection'
import type { ChildCollectionConfig, ChildRecordProps } from './NetworkChildCollection'
import type { CircuitDetail, CircuitSummary, CircuitWrite, HandoffDetail, NetworksClient } from './api'
import { networkText as t } from './networkText'

const circuitColumns = ['name', 'provider_name', 'service_identifier', 'kind', 'status', 'bandwidth_down_mbps'] as const
const circuitLabels = { name: t('name'), provider_name: t('circuitProvider'), service_identifier: t('circuitIdentifier'), kind: t('circuitKind'), status: translate('collections.status'), bandwidth_down_mbps: t('circuitDownload') }
const statuses = ['ordered', 'provisioning', 'active', 'suspended', 'disconnected'] as const
const kinds = ['internet', 'wan', 'mpls', 'dark_fiber', 'broadband', 'cellular', 'voice', 'other'] as const
const valueNames = [...statuses, ...kinds, 'overdue', 'today', 'upcoming', 'copper', 'fiber', 'coax', 'wireless', 'virtual', 'a', 'z'] as const
const valueLabels = Object.fromEntries(valueNames.map(value => [value, t(`circuitValue_${value}`)]))
const label = (value: string) => valueLabels[value] ?? value
const circuitConfig: ChildCollectionConfig<CircuitSummary, CircuitDetail> = {
  key: 'circuits', feature: 'network-circuits', childSelectionKeys: ['handoff', 'handoff_section', 'handoff_history_page'], columns: circuitColumns, labels: circuitLabels,
  title: t('circuits'), back: t('circuitBack'), create: t('circuitNew'), search: t('circuitSearch'), order: t('circuitOrder'), failed: t('circuitFailed'), empty: t('circuitEmpty'), count: count => t('circuitCount', { count }),
  statuses: statuses.map(value => ({ value, label: label(value) })), association: { label: t('circuitKind'), choices: kinds.map(value => ({ value, label: label(value) })) },
  identity: row => row.name, value: (row, column) => column === 'kind' || column === 'status' ? label(row[column]) : row[column as keyof CircuitSummary] ?? t('circuitMissing'),
  load: (client, workspace, query, signal) => client.circuitCollection(workspace, query, signal), read: (client, workspace, id, signal) => client.circuitDetail(workspace, id, signal),
}
type Context = { workspace: WorkspaceContext; client: NetworksClient; parentId: string }
export function CircuitRegister({ workspace, client, preferenceClient = browserCollectionPreferences }: Omit<Context, 'parentId'> & { preferenceClient?: typeof browserCollectionPreferences }) {
  return <NetworkChildCollection standalone workspace={workspace} client={client} preferenceClient={preferenceClient} config={circuitConfig} RecordComponent={CircuitView} />
}
const dateFields = ['installed_on', 'service_starts_on', 'review_on', 'planned_disconnect_on'] as const
const dateLabels = { installed_on: t('circuitInstalled'), service_starts_on: t('circuitStarts'), review_on: t('circuitReview'), planned_disconnect_on: t('circuitDisconnect') }
function CircuitView({ record, workspace, client, canManage, onSaved, onReturn }: ChildRecordProps<CircuitDetail> & Context) {
  const [assignment, setAssignment] = useState(false)
  const [params] = useSearchParams(), location = useLocation()
  const section = ['handoffs', 'history'].includes(params.get('circuits_section') ?? '') ? params.get('circuits_section')! : 'overview'
  const initial = { name: record?.name ?? '', service_identifier: record?.service_identifier ?? '', bandwidth_down_mbps: record?.bandwidth_down_mbps ?? null, bandwidth_up_mbps: record?.bandwidth_up_mbps ?? null, installed_on: record?.installed_on ?? null, service_starts_on: record?.service_starts_on ?? null, review_on: record?.review_on ?? null, planned_disconnect_on: record?.planned_disconnect_on ?? null, description: record?.description ?? '' }
  const [form, setForm] = useState(initial), [editing, setEditing] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const attempt = useUnsavedChanges(editing && JSON.stringify(form) !== JSON.stringify(initial), busy, () => { setEditing(false); setForm(initial) }, editing)
  const handoffConfig = useMemo(() => handoffs(record?.id ?? ''), [record?.id])
  async function save() {
    if (!record || busy) return
    setBusy(true); setError('')
    try { const saved = await client.updateCircuit(workspace, record.id, form satisfies Partial<CircuitWrite>); setEditing(false); onSaved(saved) }
    catch (caught) { setError(caught instanceof Error ? caught.message : t('circuitSaveFailed')) } finally { setBusy(false) }
  }
  function href(id: string) { const next = new URLSearchParams(params); next.set('circuits_section', id); return `${location.pathname}?${next}` }
  if (!record) return canManage ? <CircuitEditor record={null} workspace={workspace} client={client} canManage={canManage} onSaved={onSaved} onReturn={onReturn} onCancel={onReturn} /> : <p>{t('circuitUnavailable')}</p>
  if (assignment) return <CircuitEditor record={record} workspace={workspace} client={client} canManage={canManage} onSaved={onSaved} onReturn={onReturn} onCancel={() => setAssignment(false)} />
  return <article className="record-page">
    {params.get('circuits_full') === 'true' && <RecordHeader title={record.name} recordId={record.id} section={section} />}
    <RecordSections current={section} sections={['overview', 'handoffs', 'history'].map(id => ({ id, label: id === 'handoffs' ? t('circuitHandoffs') : translate(id === 'overview' ? 'collections.overview' : 'collections.history'), href: href(id) }))} />
    {section === 'handoffs' ? <NetworkChildCollection workspace={workspace} parentId={record.id} client={client} config={handoffConfig} RecordComponent={HandoffView} /> : section === 'history' ? <RecordActivity workspace={workspace} entityId={record.id} description={t('circuitHistoryHelp')} emptyLabel={t('circuitHistoryEmpty')} deniedLabel={t('circuitHistoryDenied')} actionLabels={{ 'network_circuit.created': t('circuitCreated'), 'network_circuit.updated': t('circuitUpdated') }} /> : <>
      {error && <p role="alert">{error}</p>}
      {editing && canManage ? <form className="network-inline-editor" onSubmit={event => { event.preventDefault(); void save() }}><fieldset disabled={busy}><div className="field-grid">
        <label>{t('name')}<input required maxLength={240} value={form.name} onChange={event => setForm({ ...form, name: event.target.value })} /></label>
        <label>{t('circuitIdentifier')}<input required maxLength={240} value={form.service_identifier} onChange={event => setForm({ ...form, service_identifier: event.target.value })} /></label>
        {(['bandwidth_down_mbps', 'bandwidth_up_mbps'] as const).map(field => <label key={field}>{field === 'bandwidth_down_mbps' ? t('circuitDownload') : t('circuitUpload')}<input type="number" min="0.001" step="0.001" value={form[field] ?? ''} onChange={event => setForm({ ...form, [field]: event.target.value || null })} /></label>)}
        {dateFields.map(field => <label key={field}>{dateLabels[field]}<input type="date" value={form[field] ?? ''} onChange={event => setForm({ ...form, [field]: event.target.value || null })} /></label>)}
      </div><label>{t('description')}<textarea rows={4} maxLength={4000} value={form.description} onChange={event => setForm({ ...form, description: event.target.value })} /></label><div className="form-actions"><button className="primary-button">{busy ? translate('common.saving') : t('circuitSave')}</button><button type="button" className="secondary-button" onClick={() => attempt(() => setEditing(false))}>{translate('common.cancel')}</button></div></fieldset></form> : <>
        <dl className="record-facts">{circuitColumns.map(field => <div key={field}><dt>{circuitLabels[field]}</dt><dd>{field === 'kind' || field === 'status' ? label(record[field]) : record[field] ?? t('circuitMissing')}</dd></div>)}<div><dt>{t('circuitUpload')}</dt><dd>{record.bandwidth_up_mbps ?? t('circuitMissing')}</dd></div>{dateFields.map(field => <div key={field}><dt>{dateLabels[field]}</dt><dd>{record[field] ?? t('circuitMissing')}</dd></div>)}{record.contract && <div><dt>{t('circuitContract')}</dt><dd>{record.contract.name}</dd></div>}</dl>
        <p className="network-notes">{record.description || t('noDescription')}</p>
        {canManage && <button type="button" className="secondary-button" onClick={() => { setForm(initial); setEditing(true) }}>{t('circuitEdit')}</button>}
        {canManage && 'contract' in record && <button type="button" className="secondary-button" onClick={() => setAssignment(true)}>{t('circuitAssignmentEdit')}</button>}
      </>}
      <h2>{t('circuitDates')}</h2>{record.lifecycle_events.length ? <ul className="plain-detail-list">{record.lifecycle_events.map(event => <li key={`${event.kind}-${event.date}`}><span>{event.date} · {event.label} · {label(event.state)}</span></li>)}</ul> : <p>{t('circuitDatesEmpty')}</p>}
    </>}
  </article>
}
function handoffs(parentId: string): ChildCollectionConfig<HandoffDetail, HandoffDetail> {
  return { key: 'handoff', childSelectionKeys: ['handoff_section', 'handoff_history_page'], feature: 'circuit-handoffs', parentField: 'circuit_id', columns: ['name', 'side', 'media', 'site_name'], labels: { name: t('name'), side: t('circuitSide'), media: t('circuitMedia'), site_name: t('site') }, title: t('circuitHandoffs'), back: t('circuitHandoffsBack'), create: t('circuitHandoffNew'), search: t('circuitHandoffSearch'), order: t('circuitHandoffOrder'), failed: t('circuitHandoffFailed'), empty: t('circuitHandoffEmpty'), count: count => t('circuitHandoffCount', { count }), statuses: [], association: { label: t('circuitSide'), choices: ['a', 'z'].map(value => ({ value, label: label(value) })) }, identity: row => row.name, value: (row, column) => column === 'side' || column === 'media' ? label(row[column]) : row.site_name ?? t('circuitMissing'), load: (client, workspace, query, signal) => client.handoffCollection(workspace, parentId, query, signal), read: (client, workspace, id, signal) => client.handoffDetail(workspace, parentId, id, signal) }
}
