import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router'
import { browserCollectionPreferences } from '../collections/preferences'
import { translate } from '../i18n/localization'
import { CollectionPagination } from '../CollectionPagination'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import { RecordActivity } from '../records/RecordActivity'
import { RecordHeader, RecordSections } from '../records/RecordNavigation'
import type { WorkspaceContext } from '../workspaces/api'
import { NetworkChildCollection } from './NetworkChildCollection'
import type { ChildCollectionConfig, ChildRecordProps } from './NetworkChildCollection'
import type { DNSZone, DNSRecord, DNSRecordWrite, NetworksClient } from './api'
import { networkText as t } from './networkText'
import { DNSIPChoice } from './DNSIPChoice'
const types = ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'SRV', 'CAA', 'NS', 'PTR'] as const
const zoneConfig: ChildCollectionConfig<Omit<DNSZone, 'description'>, DNSZone> = {
  key: 'dns', feature: 'dns-zones', childSelectionKeys: ['dns_record', 'dns_record_view', 'dns_record_history_page'], columns: ['name', 'record_count'], labels: { name: t('dnsZone'), record_count: t('dnsRecords') },
  title: t('dns'), back: t('dnsBack'), create: t('dnsNew'), search: t('dnsSearch'), order: t('dnsOrder'), failed: t('dnsFailed'), empty: t('dnsEmpty'), count: count => t('dnsCount', { count }), statuses: [],
  identity: row => row.name, value: row => row.record_count,
  load: (client, workspace, query, signal) => client.dnsZoneCollection(workspace, query, signal), read: (client, workspace, id, signal) => client.dnsZoneDetail(workspace, id, signal),
}
const recordConfig: ChildCollectionConfig<Omit<DNSRecord, 'description'>, DNSRecord> = {
  key: 'dns_record', childSelectionKeys: ['dns_record_view', 'dns_record_history_page'], feature: 'dns-records', parentField: 'zone_id', columns: ['name', 'record_type', 'value', 'ttl'], labels: { name: t('dnsOwner'), record_type: t('dnsType'), value: t('dnsValue'), ttl: t('dnsTTL') },
  title: t('dnsRecords'), back: t('dnsRecordsBack'), create: t('dnsRecordNew'), search: t('dnsRecordSearch'), order: t('dnsRecordOrder'), failed: t('dnsRecordFailed'), empty: t('dnsRecordEmpty'), count: count => t('dnsRecordCount', { count }), statuses: [], association: { label: t('dnsType'), choices: types.map(value => ({ value, label: value })) },
  identity: row => row.owner_name, value: (row, column) => column === 'value' ? <span className="collection-name" style={{ fontWeight: 400 }}>{row.value}</span> : row[column as 'record_type' | 'ttl'],
  load: (client, workspace, query, signal) => client.dnsRecordCollection(workspace, query, signal), read: (client, workspace, id, signal) => client.dnsRecordDetail(workspace, id, signal),
}
type Context = { workspace: WorkspaceContext; client: NetworksClient; parentId: string }
export function DNSRegister({ workspace, client, preferenceClient = browserCollectionPreferences }: Omit<Context, 'parentId'> & { preferenceClient?: typeof browserCollectionPreferences }) {
  return <NetworkChildCollection standalone workspace={workspace} client={client} preferenceClient={preferenceClient} config={zoneConfig} RecordComponent={ZoneView} />
}
function ZoneView({ record, workspace, client, canManage, onSaved, onReturn }: ChildRecordProps<DNSZone> & Context) {
  const [params] = useSearchParams(), location = useLocation()
  const section = ['records', 'history'].includes(params.get('dns_section') ?? '') ? params.get('dns_section')! : 'overview'
  const initial = { name: record?.name ?? '', description: record?.description ?? '' }
  const [form, setForm] = useState(initial), [editing, setEditing] = useState(!record), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const attempt = useUnsavedChanges(editing && JSON.stringify(form) !== JSON.stringify(initial), busy, () => { setEditing(false); setForm(initial) }, editing)
  async function save() {
    if (busy) return
    setBusy(true); setError('')
    try { const saved = await (record ? client.updateDNSZone(workspace, record.id, form) : client.createDNSZone(workspace, form)); setEditing(false); onSaved(saved) }
    catch (caught) { setError(caught instanceof Error ? caught.message : t('dnsSaveFailed')) } finally { setBusy(false) }
  }
  function href(id: string) { const next = new URLSearchParams(params); next.set('dns_section', id); return `${location.pathname}?${next}` }
  return <article className="record-page">
    {params.get('dns_full') === 'true' && <RecordHeader title={record?.name ?? t('dnsNew')} recordId={record?.id ?? 'new'} section={section} />}
    {record && <RecordSections current={section} sections={['overview', 'records', 'history'].map(id => ({ id, label: id === 'records' ? t('dnsRecords') : translate(id === 'overview' ? 'collections.overview' : 'collections.history'), href: href(id) }))} />}
    {section === 'records' && record ? <NetworkChildCollection workspace={workspace} parentId={record.id} client={client} config={recordConfig} RecordComponent={DNSRecordView} /> : section === 'history' && record ? <RecordActivity workspace={workspace} entityId={record.id} description={t('dnsHistoryHelp')} emptyLabel={t('dnsHistoryEmpty')} deniedLabel={t('dnsHistoryDenied')} actionLabels={{ 'dns_zone.created': t('dnsZoneCreated'), 'dns_zone.updated': t('dnsZoneUpdated') }} /> : <>
      {error && <p role="alert">{error}</p>}
      {editing && canManage ? <form className="network-inline-editor" onSubmit={event => { event.preventDefault(); void save() }}><fieldset disabled={busy}>
        <label>{t('dnsZoneName')}<input required maxLength={253} value={form.name} onChange={event => setForm({ ...form, name: event.target.value })} /></label>
        {Boolean(record?.record_count) && <p>{t('dnsRenameHelp')}</p>}
        <label>{t('description')}<textarea rows={4} maxLength={4000} value={form.description} onChange={event => setForm({ ...form, description: event.target.value })} /></label>
        <div className="form-actions"><button className="primary-button">{busy ? translate('common.saving') : t('dnsSave')}</button><button type="button" className="secondary-button" onClick={() => record ? attempt(() => setEditing(false)) : onReturn()}>{translate('common.cancel')}</button></div>
      </fieldset></form> : record ? <>
        <dl className="record-facts"><div><dt>{t('dnsZone')}</dt><dd>{record.name}</dd></div></dl>
        <p>{t('dnsInventoryHelp')}</p><p className="network-notes">{record.description || t('noDescription')}</p>
        {canManage && <button type="button" className="secondary-button" onClick={() => { setForm(initial); setEditing(true) }}>{t('dnsEdit')}</button>}
      </> : <p>{t('dnsDenied')}</p>}
    </>}
  </article>
}
function DNSRecordView({ record, workspace, client, parentId, canManage, onSaved, onReturn }: ChildRecordProps<DNSRecord> & Context) {
  const [params] = useSearchParams(), location = useLocation()
  const history = Boolean(record) && params.get('dns_record_view') === 'history'
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [record?.id, history])
  function href(showHistory: boolean) {
    const next = new URLSearchParams(params)
    if (showHistory) next.set('dns_record_view', 'history')
    else next.delete('dns_record_view')
    return `${location.pathname}?${next}`
  }

  const initial: DNSRecordWrite = { zone_id: parentId, owner_name: record?.owner_name ?? '', record_type: record?.record_type ?? 'A', value: record?.value ?? '', ttl: record?.ttl ?? 3600, priority: record?.priority ?? null, weight: record?.weight ?? null, port: record?.port ?? null, ip_address_id: record?.ip_address_id ?? null, description: record?.description ?? '' }
  const [form, setForm] = useState(initial), [editing, setEditing] = useState(!record), [moving, setMoving] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const attempt = useUnsavedChanges(editing && JSON.stringify(form) !== JSON.stringify(initial), busy, () => { setEditing(false); setForm(initial); setMoving(false) }, editing)
  async function save() {
    if (busy) return
    setBusy(true); setError('')
    try {
      const changes: Partial<DNSRecordWrite> = { ...form }
      delete changes.zone_id
      const saved = await (record ? client.updateDNSRecord(workspace, record.id, changes) : client.createDNSRecord(workspace, form))
      setEditing(false); onSaved(saved)
    } catch (caught) { setError(caught instanceof Error ? caught.message : t('dnsSaveFailed')) } finally { setBusy(false) }
  }
  return <section>
    <button type="button" className="secondary-button" onClick={onReturn}>{t('dnsRecordsBack')}</button><h2 ref={heading} tabIndex={-1}>{record?.owner_name ?? t('dnsRecordNew')}</h2>
    {record && <p><Link to={href(!history)} state={location.state as unknown}>{t(history ? 'dnsRecordDetailsBack' : 'dnsRecordHistoryOpen')}</Link></p>}
    {history && record ? <RecordActivity workspace={workspace} entityId={record.id} pageParameter="dns_record_history_page" description={t('dnsRecordHistoryHelp')} emptyLabel={t('dnsRecordHistoryEmpty')} deniedLabel={t('dnsRecordHistoryDenied')} actionLabels={{ 'dns_record.created': t('dnsRecordCreated'), 'dns_record.updated': t('dnsRecordUpdated') }} /> : <>
    {error && <p role="alert">{error}</p>}
    {moving && record && canManage ? <DNSRecordTransfer record={record} workspace={workspace} client={client} onSaved={(saved) => { setMoving(false); onSaved(saved) }} onCancel={() => setMoving(false)} /> : editing && canManage ? <form className="network-inline-editor" onSubmit={event => { event.preventDefault(); void save() }}><fieldset disabled={busy}>
      <div className="field-grid">
        <label>{t('dnsOwner')}<input required maxLength={253} value={form.owner_name} onChange={event => setForm({ ...form, owner_name: event.target.value })} /></label>
        <label>{t('dnsType')}<select value={form.record_type} onChange={event => setForm({ ...form, record_type: event.target.value as DNSRecordWrite['record_type'], priority: null, weight: null, port: null, ip_address_id: null })}>{types.map(type => <option key={type}>{type}</option>)}</select></label>
        <label>{t('dnsValue')}<textarea required maxLength={4096} rows={3} value={form.value} onChange={event => setForm({ ...form, value: event.target.value })} /></label>
        <label>{t('dnsTTL')}<input required type="number" min={0} max={2147483647} value={form.ttl} onChange={event => setForm({ ...form, ttl: Number(event.target.value) })} /></label>
        {(form.record_type === 'MX' || form.record_type === 'SRV') && <label>{t('dnsPriority')}<input required type="number" min={0} max={65535} value={form.priority ?? ''} onChange={event => setForm({ ...form, priority: event.target.value === '' ? null : Number(event.target.value) })} /></label>}
        {form.record_type === 'SRV' && (['weight', 'port'] as const).map(field => <label key={field}>{t(field === 'weight' ? 'dnsWeight' : 'dnsPort')}<input required type="number" min={0} max={65535} value={form[field] ?? ''} onChange={event => setForm({ ...form, [field]: event.target.value === '' ? null : Number(event.target.value) })} /></label>)}
      </div>
      {(form.record_type === 'A' || form.record_type === 'AAAA') && <DNSIPChoice workspace={workspace} client={client} selectedId={form.ip_address_id} family={form.record_type === 'A' ? 4 : 6} onChange={ip => setForm({ ...form, ip_address_id: ip?.id ?? null, value: ip?.address ?? form.value })} />}
      <label>{t('description')}<textarea rows={4} maxLength={4000} value={form.description} onChange={event => setForm({ ...form, description: event.target.value })} /></label>
      <div className="form-actions"><button className="primary-button">{busy ? translate('common.saving') : t('dnsRecordSave')}</button><button type="button" className="secondary-button" onClick={() => record ? attempt(() => setEditing(false)) : onReturn()}>{translate('common.cancel')}</button></div>
    </fieldset></form> : record ? <>
      <dl className="record-facts">{(['record_type', 'value', 'ttl', 'priority', 'weight', 'port'] as const).map(field => record[field] !== null && <div key={field}><dt>{({ record_type: t('dnsType'), value: t('dnsValue'), ttl: t('dnsTTL'), priority: t('dnsPriority'), weight: t('dnsWeight'), port: t('dnsPort') })[field]}</dt><dd>{record[field]}</dd></div>)}{record.ip_address_id && <div><dt>{t('dnsIP')}</dt><dd>{record.value}</dd></div>}</dl>
      <p className="network-notes">{record.description || t('noDescription')}</p>
      {canManage && <div className="form-actions"><button type="button" className="secondary-button" onClick={() => { setForm(initial); setError(''); setEditing(true) }}>{t('dnsRecordEdit')}</button><button type="button" className="secondary-button" onClick={() => { setError(''); setMoving(true) }}>{t('dnsRecordMove')}</button></div>}
    </> : <p>{t('dnsDenied')}</p>}
    </>}
  </section>
}

function DNSRecordTransfer({ record, workspace, client, onSaved, onCancel }: { record: DNSRecord; workspace: WorkspaceContext; client: NetworksClient; onSaved: (record: DNSRecord) => void; onCancel: () => void }) {
  type Choice = Awaited<ReturnType<NetworksClient['dnsZoneCollection']>>['results'][number]
  const [search, setSearch] = useState(''), [draft, setDraft] = useState(''), [page, setPage] = useState(1), [reload, setReload] = useState(0)
  const [selected, setSelected] = useState<Choice | null>(null), [ownerName, setOwnerName] = useState(record.owner_name)
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [response, setResponse] = useState<{ key: string; value?: Awaited<ReturnType<NetworksClient['dnsZoneCollection']>> } | null>(null)
  const key = `${workspace.kind}:${workspace.id}:${page}:${search}`
  const result = response?.key === key ? response : null
  const choices = result?.value?.results.filter((row) => row.id !== record.zone_id) ?? []
  const dirty = Boolean(selected || draft || search || ownerName !== record.owner_name)
  const attempt = useUnsavedChanges(dirty, busy, () => { setSelected(null); setOwnerName(record.owner_name) }, true)
  useEffect(() => {
    const controller = new AbortController()
    client.dnsZoneCollection(workspace, { q: search, page, page_size: 25, ordering: 'name' }, controller.signal).then((value) => { if (!controller.signal.aborted) setResponse({ key, value }) }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) })
    return () => controller.abort()
  }, [workspace, client, search, page, key, reload])
  function suggestedOwner(zoneName: string) {
    if (record.owner_name === record.zone_name) return zoneName
    const suffix = `.${record.zone_name}`
    return record.owner_name.endsWith(suffix) ? `${record.owner_name.slice(0, -suffix.length)}.${zoneName}` : record.owner_name
  }
  function find() { setSearch(draft); setPage(1) }
  async function save() {
    if (busy) return
    if (!selected) { setError(t('dnsRecordMoveRequired')); return }
    setBusy(true); setError('')
    try {
      const value = await client.moveDNSRecord(workspace, record.id, selected.id, record.zone_id, ownerName)
      setSelected(null); setDraft(''); setSearch(''); setOwnerName(record.owner_name); onSaved(value)
    } catch (caught) { setError(caught instanceof Error ? caught.message : t('dnsSaveFailed')) } finally { setBusy(false) }
  }
  return <section aria-label={t('dnsRecordMove')}>
    <p>{t('dnsRecordMoveHelp')}</p>
    {error && <p role="alert">{error}</p>}
    <p>{t('dnsRecordMoveSelected')}: <strong>{selected?.name ?? t('dnsRecordMoveChoose')}</strong></p>
    <div className="collection-search"><input type="search" maxLength={253} aria-label={t('dnsRecordMoveSearch')} value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); find() } }} /><button type="button" className="secondary-button" onClick={find}>{translate('collections.searchAction')}</button></div>
    {!result ? <p role="status">{translate('collections.loading')}</p> : !result.value ? <p role="alert">{t('dnsRecordMoveFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
      {choices.length || selected ? <label>{t('dnsRecordMoveChoices')}<select value={selected?.id ?? ''} onChange={event => { const row = choices.find(item => item.id === event.target.value); setSelected(row ?? null); setOwnerName(row ? suggestedOwner(row.name) : record.owner_name) }}><option value="">{t('dnsRecordMoveChoose')}</option>{selected && !choices.some(row => row.id === selected.id) && <option value={selected.id}>{selected.name}</option>}{choices.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label> : <p>{t('dnsRecordMoveEmpty')}</p>}
      <CollectionPagination label={t('dnsRecordMoveChoices')} page={page} pageSize={25} count={result.value.count} hasMore={result.value.has_more} onPageChange={setPage} />
    </>}
    <label>{t('dnsRecordMoveOwner')}<input required maxLength={253} value={ownerName} onChange={event => setOwnerName(event.target.value)} /></label>
    <p>{t('dnsRecordMoveOwnerHelp')}</p>
    <div className="form-actions"><button type="button" className="primary-button" disabled={busy} onClick={() => void save()}>{busy ? translate('common.saving') : t('dnsRecordMoveSave')}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => attempt(onCancel)}>{translate('common.cancel')}</button></div>
  </section>
}
