import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Pencil, Plus, Search, UserPlus, X } from 'lucide-react'
import { useSearchParams } from 'react-router'
import type { Dispatch, FormEvent, SetStateAction } from 'react'
import { QuickDrawer } from '../collections/QuickDrawer'
import '../collections/collections.css'
import { FilterMenu } from '../FilterMenu'
import { translate } from '../i18n/localization'
import { useNavigationGuardStatus, useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { InventoryClient, LicenseOrdering, LicenseQuery, LicenseResult, SoftwareChoices, SoftwareLicense } from './api'

type LicenseMode = 'read' | 'edit' | 'seat' | 'link'
type LicenseFormState = {
  name: string
  asset_id: string
  kind: SoftwareLicense['kind']
  status: SoftwareLicense['status']
  seat_limit: number
  starts_on: string
  renews_on: string
  ends_on: string
  renewal_interval: SoftwareLicense['renewal_interval']
  auto_renew: boolean
  reference: string
}
type SeatFormState = { person_id: string; installation_id: string }

const BLANK_FORM: LicenseFormState = {
  name: '', asset_id: '', kind: 'subscription', status: 'active', seat_limit: 1,
  starts_on: '', renews_on: '', ends_on: '', renewal_interval: 'annual', auto_renew: true, reference: '',
}
const INITIAL_QUERY: LicenseQuery = { q: '', kind: '', status: '', ordering: 'name', page: 1, page_size: 25 }

function initialQuery(parameters: URLSearchParams): LicenseQuery {
  const ordering = parameters.get('license_order')
  const kind = parameters.get('license_kind')
  const status = parameters.get('license_status')
  const page = Number(parameters.get('license_page'))
  return {
    ...INITIAL_QUERY,
    q: parameters.get('q') ?? '',
    kind: ['subscription', 'perpetual', 'trial'].includes(kind ?? '') ? kind as LicenseQuery['kind'] : '',
    status: ['active', 'suspended', 'expired', 'terminated'].includes(status ?? '') ? status as LicenseQuery['status'] : '',
    ordering: ['name', '-name', 'renews_on', '-renews_on'].includes(ordering ?? '') ? ordering as LicenseOrdering : 'name',
    page: Number.isInteger(page) && page > 0 ? page : 1,
  }
}

function formFromLicense(record: SoftwareLicense): LicenseFormState {
  return {
    name: record.name, asset_id: '', kind: record.kind, status: record.status, seat_limit: record.seat_limit,
    starts_on: record.starts_on ?? '', renews_on: record.renews_on ?? '', ends_on: record.ends_on ?? '',
    renewal_interval: record.renewal_interval, auto_renew: record.auto_renew, reference: record.reference,
  }
}

function payloadFromForm(form: LicenseFormState) {
  const perpetual = form.kind === 'perpetual'
  return {
    name: form.name, asset_id: form.asset_id, kind: form.kind, status: form.status, seat_limit: Number(form.seat_limit),
    starts_on: form.starts_on || null, renews_on: form.renews_on || null, ends_on: form.ends_on || null,
    renewal_interval: perpetual ? 'none' : form.renewal_interval, auto_renew: perpetual ? false : form.auto_renew,
    reference: form.reference,
  }
}

function updatePayloadFromForm(form: LicenseFormState) {
  const payload = payloadFromForm(form)
  return {
    name: payload.name, kind: payload.kind, status: payload.status, seat_limit: payload.seat_limit,
    starts_on: payload.starts_on, renews_on: payload.renews_on, ends_on: payload.ends_on,
    renewal_interval: payload.renewal_interval, auto_renew: payload.auto_renew, reference: payload.reference,
  }
}

export function Licenses({ workspace, client }: { workspace: WorkspaceContext; client: InventoryClient }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState<LicenseQuery>(() => initialQuery(searchParams))
  const [loaded, setLoaded] = useState<{ scope: string; result: LicenseResult } | null>(null)
  const [selected, setSelected] = useState<{ scope: string; record: SoftwareLicense } | null>(null)
  const [choices, setChoices] = useState<SoftwareChoices>({ installations: [], people: [] })
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [drawerErrorId, setDrawerErrorId] = useState<string | null>(null)
  const [mode, setMode] = useState<LicenseMode>('read')
  const [form, setForm] = useState<LicenseFormState>(BLANK_FORM)
  const [seat, setSeat] = useState<SeatFormState>({ person_id: '', installation_id: '' })
  const [linkId, setLinkId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [createdRecordId, setCreatedRecordId] = useState<string | null>(null)
  const scope = `${workspace.kind}:${workspace.id}`
  const drawerId = searchParams.get('license')
  const creating = drawerId === 'new'
  const result = loaded?.scope === scope ? loaded.result : null
  const listed = drawerId && !creating ? result?.results.find((record) => record.id === drawerId) : null
  const drawerRecord = listed ?? (selected?.scope === scope && selected.record.id === drawerId ? selected.record : null)
  const visiblePhase = loaded && loaded.scope !== scope ? 'loading' : phase
  const drawerPhase = creating ? 'ready' : drawerErrorId === drawerId ? 'error' : drawerRecord ? 'ready' : 'loading'
  const activeMode = creating ? 'edit' : mode
  const dirty = creating
    ? JSON.stringify(form) !== JSON.stringify(BLANK_FORM)
    : mode === 'edit' && drawerRecord
      ? JSON.stringify(form) !== JSON.stringify(formFromLicense(drawerRecord))
      : mode === 'seat' ? Boolean(seat.person_id || seat.installation_id)
        : mode === 'link' ? Boolean(linkId) : false

  const discard = useCallback(() => {
    setMode('read'); setForm(BLANK_FORM); setSeat({ person_id: '', installation_id: '' }); setLinkId(''); setError(null)
  }, [])
  const attempt = useUnsavedChanges(dirty, busy, discard, Boolean(drawerId && activeMode !== 'read'))
  const navigationGuarded = useNavigationGuardStatus()

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      Promise.all([client.listLicenses(workspace, query, controller.signal), client.softwareChoices(workspace)])
        .then(([next, available]) => {
          if (!controller.signal.aborted) { setLoaded({ scope, result: next }); setChoices(available); setPhase('ready') }
        })
        .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, query, refresh, scope, workspace])

  useEffect(() => {
    if (!drawerId || creating || listed) return
    const controller = new AbortController()
    client.retrieveLicense(workspace, drawerId, controller.signal)
      .then((record) => { if (!controller.signal.aborted) { setSelected({ scope, record }); setDrawerErrorId(null) } })
      .catch(() => { if (!controller.signal.aborted) setDrawerErrorId(drawerId) })
    return () => controller.abort()
  }, [client, creating, drawerId, listed, scope, workspace])

  const updateDrawerUrl = useCallback((id: string | null, replace = false) => {
    const next = new URLSearchParams(searchParams)
    if (id) next.set('license', id); else next.delete('license')
    setSearchParams(next, { replace })
  }, [searchParams, setSearchParams])

  useEffect(() => {
    if (!createdRecordId || dirty || busy || navigationGuarded) return
    const timer = window.setTimeout(() => {
      updateDrawerUrl(createdRecordId, true)
      setCreatedRecordId(null)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [busy, createdRecordId, dirty, navigationGuarded, updateDrawerUrl])

  function changeQuery(changes: Partial<LicenseQuery>) {
    const nextQuery = { ...query, ...changes, page: changes.page ?? 1 }
    const next = new URLSearchParams(searchParams)
    if (nextQuery.q) next.set('q', nextQuery.q); else next.delete('q')
    if (nextQuery.kind) next.set('license_kind', nextQuery.kind); else next.delete('license_kind')
    if (nextQuery.status) next.set('license_status', nextQuery.status); else next.delete('license_status')
    if (nextQuery.ordering !== 'name') next.set('license_order', nextQuery.ordering); else next.delete('license_order')
    if (nextQuery.page > 1) next.set('license_page', String(nextQuery.page)); else next.delete('license_page')
    setQuery(nextQuery); setSearchParams(next, { replace: true })
  }

  function sort(field: 'name' | 'renews_on') { changeQuery({ ordering: query.ordering === field ? `-${field}` : field }) }
  function sortIndicator(field: string) { return query.ordering === field ? <ArrowUp size={13} aria-hidden="true" /> : query.ordering === `-${field}` ? <ArrowDown size={13} aria-hidden="true" /> : null }
  function openRecord(record: SoftwareLicense) { discard(); setSelected({ scope, record }); setDrawerErrorId(null); updateDrawerUrl(record.id) }
  function startCreate() { discard(); setForm(BLANK_FORM); updateDrawerUrl('new') }
  function closeDrawer() { attempt(() => { discard(); window.setTimeout(() => updateDrawerUrl(null), 0) }) }
  function replace(record: SoftwareLicense) {
    setSelected({ scope, record })
    setLoaded((current) => current?.scope === scope ? { ...current, result: { ...current.result, results: current.result.results.map((item) => item.id === record.id ? record : item) } } : current)
    discard(); setRefresh((value) => value + 1)
  }
  async function perform(action: () => Promise<SoftwareLicense>, created = false) {
    setBusy(true); setError(null)
    try {
      const record = await action(); replace(record)
      if (created) setCreatedRecordId(record.id)
    } catch (caught) { setError(caught instanceof Error ? caught.message : translate('licenses.changeFailed')) }
    finally { setBusy(false) }
  }

  const rangeStart = result?.count ? (result.page - 1) * result.page_size + 1 : 0
  const rangeEnd = result ? Math.min(result.page * result.page_size, result.count) : 0
  const countLabel = useMemo(() => result ? translate('pagination.range', { first: rangeStart, last: rangeEnd, count: result.count }) : translate('common.loading'), [rangeEnd, rangeStart, result])
  const returnHref = workspace.kind === 'msp' ? '/licenses' : `/workspaces/organizations/${workspace.id}/licenses`

  return <>
    <header className="page-header"><div><h1>{translate('licenses.heading')}</h1><p>{translate('licenses.pageHelp')}</p></div>{result?.can_manage && <button type="button" className="primary-button" onClick={startCreate}><Plus size={16} aria-hidden="true" /><span>{translate('licenses.new')}</span></button>}</header>
    {drawerId && <QuickDrawer title={creating ? translate('licenses.newSoftware') : drawerRecord?.name ?? translate('licenses.record')} onClose={closeDrawer} returnFocusId={creating ? undefined : `license-row-${drawerId}`} returnHref={returnHref} returnLabel={translate('licenses.back')}>
      {error && <div className="form-message error" role="alert">{error}</div>}
      {drawerPhase === 'loading' && <p role="status">{translate('licenses.loadingRecord')}</p>}
      {drawerPhase === 'error' && <div className="workspace-error" role="alert"><h3>{translate('licenses.recordUnavailable')}</h3><p>{translate('licenses.recordUnavailableHelp')}</p></div>}
      {creating && <LicenseForm title={translate('licenses.newSoftware')} form={form} setForm={setForm} choices={choices} busy={busy} requireInstallation cancel={closeDrawer} submit={() => void perform(() => client.createLicense(workspace, payloadFromForm(form)), true)} />}
      {drawerPhase === 'ready' && drawerRecord && <LicenseDetail record={drawerRecord} canManage={Boolean(result?.can_manage)} choices={choices} mode={mode} setMode={setMode} seat={seat} setSeat={setSeat} linkId={linkId} setLinkId={setLinkId} busy={busy} attempt={attempt} perform={perform} client={client} workspace={workspace} form={form} setForm={setForm} />}
    </QuickDrawer>}
    <section className="content-section" aria-labelledby="license-list-heading">
      <div className="section-heading"><h2 id="license-list-heading">{translate('licenses.directory')}</h2><span>{countLabel}</span></div>
      <div className="collection-toolbar"><label className="collection-search"><Search size={16} aria-hidden="true" /><span className="sr-only">{translate('licenses.search')}</span><input type="search" aria-label={translate('licenses.search')} value={query.q} onChange={(event) => changeQuery({ q: event.target.value })} placeholder={translate('licenses.searchPlaceholder')} /></label><FilterMenu activeCount={Number(Boolean(query.kind)) + Number(Boolean(query.status))} onClear={() => changeQuery({ kind: '', status: '' })} groups={[
        { kind: 'choices', label: translate('licenses.kind'), value: query.kind, choices: ['', 'subscription', 'perpetual', 'trial'].map((value) => ({ value, label: value ? translate(`licenses.kind_${value}` as 'licenses.kind_subscription') : translate('licenses.allKinds') })), onChange: (value) => changeQuery({ kind: value as LicenseQuery['kind'] }) },
        { kind: 'choices', label: translate('licenses.status'), value: query.status, choices: ['', 'active', 'suspended', 'expired', 'terminated'].map((value) => ({ value, label: value ? translate(`licenses.status_${value}` as 'licenses.status_active') : translate('licenses.allStatuses') })), onChange: (value) => changeQuery({ status: value as LicenseQuery['status'] }) },
      ]} /></div>
      {visiblePhase === 'loading' && <p role="status">{translate('licenses.loading')}</p>}
      {visiblePhase === 'error' && <div className="workspace-error" role="alert"><h2>{translate('licenses.unavailable')}</h2><p>{translate('licenses.loadFailed')}</p></div>}
      {visiblePhase === 'ready' && result?.results.length === 0 && <p className="empty-state">{translate('licenses.empty')}</p>}
      {visiblePhase === 'ready' && result && result.results.length > 0 && <div className="people-table-wrap" role="group" aria-label={translate('licenses.table')} tabIndex={0}><table className="people-table"><thead><tr><th scope="col" aria-sort={query.ordering === 'name' ? 'ascending' : query.ordering === '-name' ? 'descending' : 'none'}><button type="button" onClick={() => sort('name')}>{translate('licenses.name')}{sortIndicator('name')}</button></th><th scope="col">{translate('licenses.software')}</th><th scope="col">{translate('licenses.seats')}</th><th scope="col">{translate('licenses.status')}</th><th scope="col" aria-sort={query.ordering === 'renews_on' ? 'ascending' : query.ordering === '-renews_on' ? 'descending' : 'none'}><button type="button" onClick={() => sort('renews_on')}>{translate('licenses.renews')}{sortIndicator('renews_on')}</button></th></tr></thead><tbody>{result.results.map((record) => <tr key={record.id}><td data-label={translate('licenses.name')}><button id={`license-row-${record.id}`} className="collection-name" type="button" onClick={() => openRecord(record)}>{record.name}</button><span className="collection-secondary">{record.reference || translate('licenses.noReference')}</span></td><td data-label={translate('licenses.software')}>{record.product_name}{record.model_name ? ` · ${record.model_name}` : ''}</td><td data-label={translate('licenses.seats')}>{record.active_seats}/{record.seat_limit}</td><td data-label={translate('licenses.status')}>{translate(`licenses.status_${record.status}` as 'licenses.status_active')}</td><td data-label={translate('licenses.renews')}>{record.renews_on ?? translate('licenses.notScheduled')}</td></tr>)}</tbody></table></div>}
      {visiblePhase === 'ready' && result && result.count > result.page_size && <nav className="people-pagination" aria-label={translate('licenses.pages')}><button className="secondary-button" type="button" disabled={result.page === 1} onClick={() => changeQuery({ page: result.page - 1 })}><ChevronLeft size={15} aria-hidden="true" />{translate('pagination.previous')}</button><span>{translate('pagination.page', { page: result.page })}</span><button className="secondary-button" type="button" disabled={!result.has_more} onClick={() => changeQuery({ page: result.page + 1 })}>{translate('pagination.next')}<ChevronRight size={15} aria-hidden="true" /></button></nav>}
    </section>
  </>
}

type DetailProps = {
  record: SoftwareLicense; canManage: boolean; choices: SoftwareChoices; mode: LicenseMode; setMode: Dispatch<SetStateAction<LicenseMode>>
  seat: SeatFormState; setSeat: Dispatch<SetStateAction<SeatFormState>>; linkId: string; setLinkId: Dispatch<SetStateAction<string>>
  busy: boolean; attempt: (action: () => void) => void; perform: (action: () => Promise<SoftwareLicense>) => Promise<void>
  client: InventoryClient; workspace: WorkspaceContext; form: LicenseFormState; setForm: Dispatch<SetStateAction<LicenseFormState>>
}

function LicenseDetail({ record, canManage, choices, mode, setMode, seat, setSeat, linkId, setLinkId, busy, attempt, perform, client, workspace, form, setForm }: DetailProps) {
  if (mode === 'edit') return <LicenseForm title={translate('licenses.editHeading', { name: record.name })} form={form} setForm={setForm} choices={choices} busy={busy} cancel={() => attempt(() => setMode('read'))} submit={() => void perform(() => client.updateLicense(workspace, record.id, updatePayloadFromForm(form)))} />
  return <div className="operational-record license-record">
    <div className="section-heading"><div><h3>{translate('licenses.details')}</h3><p>{record.supplier_name} · {record.product_name}{record.model_name ? ` · ${record.model_name}` : ''}</p></div>{canManage && <button className="secondary-button" type="button" aria-label={translate('inventory.editLicense')} onClick={() => attempt(() => { setForm(formFromLicense(record)); setMode('edit') })}><Pencil size={15} aria-hidden="true" />{translate('inventory.editLicense')}</button>}</div>
    <dl className="record-facts"><div><dt>{translate('licenses.kind')}</dt><dd>{translate(`licenses.kind_${record.kind}` as 'licenses.kind_subscription')}</dd></div><div><dt>{translate('licenses.status')}</dt><dd>{translate(`licenses.status_${record.status}` as 'licenses.status_active')}</dd></div><div><dt>{translate('licenses.seats')}</dt><dd>{translate('licenses.seatSummary', { active: record.active_seats, total: record.seat_limit })}</dd></div><div><dt>{translate('licenses.renewal')}</dt><dd>{record.renews_on ?? translate('licenses.notScheduled')} · {record.auto_renew ? translate('licenses.autoRenew') : translate('licenses.manualRenewal')}</dd></div><div><dt>{translate('licenses.term')}</dt><dd>{record.starts_on ?? '—'} – {record.ends_on ?? translate('licenses.open')}</dd></div><div><dt>{translate('licenses.reference')}</dt><dd>{record.reference || translate('licenses.noReference')}</dd></div></dl>
    {canManage && mode === 'read' && <div className="operational-record-actions"><button className="secondary-button" type="button" onClick={() => attempt(() => { setSeat({ person_id: '', installation_id: '' }); setMode('seat') })}><UserPlus size={15} aria-hidden="true" />{translate('inventory.assignSeat')}</button><button className="secondary-button" type="button" onClick={() => attempt(() => { setLinkId(''); setMode('link') })}><Plus size={15} aria-hidden="true" />{translate('inventory.linkInstallation')}</button></div>}
    {mode === 'seat' && <form className="catalog-editor license-editor" onSubmit={(event) => { event.preventDefault(); void perform(() => client.assignLicenseSeat(workspace, record.id, { person_id: seat.person_id || null, installation_id: seat.installation_id || null })) }}><h3>{translate('inventory.assignSeat')}</h3><div className="catalog-form-grid"><Choice label={translate('licenses.person')} value={seat.person_id} onChange={(value) => setSeat((current) => ({ ...current, person_id: value }))} items={choices.people} /><Choice label={translate('licenses.installation')} value={seat.installation_id} onChange={(value) => setSeat((current) => ({ ...current, installation_id: value }))} items={choices.installations.map((item) => ({ id: item.id, name: item.asset_name ?? item.product_name ?? item.id }))} /></div><Actions busy={busy || (!seat.person_id && !seat.installation_id)} cancel={() => attempt(() => setMode('read'))} label={translate('inventory.assignSeat')} /></form>}
    {mode === 'link' && <form className="catalog-editor license-editor" onSubmit={(event) => { event.preventDefault(); void perform(() => client.linkLicenseInstallation(workspace, record.id, linkId)) }}><h3>{translate('inventory.linkInstallation')}</h3><div className="catalog-form-grid"><Choice label={translate('licenses.softwareInstallation')} value={linkId} onChange={setLinkId} items={choices.installations.map((item) => ({ id: item.id, name: item.asset_name ?? item.product_name ?? item.id }))} /></div><Actions busy={busy || !linkId} cancel={() => attempt(() => setMode('read'))} label={translate('inventory.linkInstallation')} /></form>}
    <section className="catalog-documents"><h3>{translate('licenses.installations')}</h3>{record.installations.length ? <ul className="inventory-list">{record.installations.map((item) => <li key={item.id}>{item.name}</li>)}</ul> : <p className="empty-state">{translate('licenses.noInstallations')}</p>}</section>
    <section className="catalog-documents"><h3>{translate('licenses.assignments')}</h3>{record.seats.filter((item) => !item.revoked_at).length === 0 ? <p className="empty-state">{translate('licenses.noAssignments')}</p> : <ul className="inventory-list">{record.seats.filter((item) => !item.revoked_at).map((item) => <li key={item.id}><span><strong>{item.person_name ?? item.installation_name ?? translate('licenses.seatNumber', { number: item.seat_number })}</strong><small>{[item.person_name && item.installation_name, translate('licenses.seatNumberLower', { number: item.seat_number })].filter(Boolean).join(' · ')}</small></span>{canManage && <button type="button" className="icon-button" title={translate('licenses.unassignSeat', { number: item.seat_number })} aria-label={translate('licenses.unassignSeat', { number: item.seat_number })} onClick={() => void perform(() => client.revokeLicenseSeat(workspace, record.id, item.id))}><X size={15} aria-hidden="true" /></button>}</li>)}</ul>}</section>
    <section className="lifecycle-history"><h3>{translate('licenses.history')}</h3>{record.events.length === 0 ? <p className="empty-state">{translate('licenses.noHistory')}</p> : <ol>{record.events.map((item) => <li key={item.id}><strong>{item.event_type.replaceAll('_', ' ')}</strong><span>{[item.person_name, item.installation_name, item.seat_number ? translate('licenses.seatNumberLower', { number: item.seat_number }) : ''].filter(Boolean).join(' · ')}</span><time dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleString()}</time></li>)}</ol>}</section>
  </div>
}

function LicenseForm({ title, form, setForm, choices, busy, requireInstallation = false, cancel, submit }: { title: string; form: LicenseFormState; setForm: Dispatch<SetStateAction<LicenseFormState>>; choices: SoftwareChoices; busy: boolean; requireInstallation?: boolean; cancel: () => void; submit: () => void }) {
  function handleSubmit(event: FormEvent) { event.preventDefault(); submit() }
  return <section className="catalog-editor license-editor"><form onSubmit={handleSubmit}><h3>{title}</h3><div className="catalog-form-grid">
    <Field label={translate('licenses.name')} value={form.name} onChange={(value) => setForm((current) => ({ ...current, name: value }))} />
    {requireInstallation && <Choice label={translate('licenses.initialInstallation')} value={form.asset_id} onChange={(value) => setForm((current) => ({ ...current, asset_id: value }))} items={choices.installations.map((item) => ({ id: item.asset_id ?? '', name: `${item.asset_name ?? translate('licenses.softwareAsset')} · ${item.product_name ?? translate('licenses.unknownProduct')}` })).filter((item) => item.id)} />}
    <label><span>{translate('licenses.kind')}</span><select value={form.kind} onChange={(event) => setForm((current) => ({ ...current, kind: event.target.value as SoftwareLicense['kind'] }))}>{['subscription', 'perpetual', 'trial'].map((value) => <option value={value} key={value}>{translate(`licenses.kind_${value}` as 'licenses.kind_subscription')}</option>)}</select></label>
    {!requireInstallation && <label><span>{translate('licenses.status')}</span><select value={form.status} onChange={(event) => setForm((current) => ({ ...current, status: event.target.value as SoftwareLicense['status'] }))}>{['active', 'suspended', 'expired', 'terminated'].map((value) => <option value={value} key={value}>{translate(`licenses.status_${value}` as 'licenses.status_active')}</option>)}</select></label>}
    <Field label={translate('licenses.seatLimit')} type="number" value={String(form.seat_limit)} onChange={(value) => setForm((current) => ({ ...current, seat_limit: Number(value) }))} />
    <Field label={translate('licenses.startsOn')} type="date" value={form.starts_on} onChange={(value) => setForm((current) => ({ ...current, starts_on: value }))} />
    <Field label={translate('licenses.renewsOn')} type="date" value={form.renews_on} onChange={(value) => setForm((current) => ({ ...current, renews_on: value }))} />
    <Field label={translate('licenses.endsOn')} type="date" value={form.ends_on} onChange={(value) => setForm((current) => ({ ...current, ends_on: value }))} />
    <label><span>{translate('licenses.renewalInterval')}</span><select value={form.renewal_interval} disabled={form.kind === 'perpetual'} onChange={(event) => setForm((current) => ({ ...current, renewal_interval: event.target.value as SoftwareLicense['renewal_interval'] }))}>{['none', 'monthly', 'annual', 'multi_year'].map((value) => <option value={value} key={value}>{translate(`licenses.interval_${value}` as 'licenses.interval_none')}</option>)}</select></label>
    <label className="checkbox-field"><input type="checkbox" checked={form.auto_renew} disabled={form.kind === 'perpetual'} onChange={(event) => setForm((current) => ({ ...current, auto_renew: event.target.checked }))} /><span>{translate('licenses.autoRenew')}</span></label>
    <Field label={translate('licenses.reference')} value={form.reference} onChange={(value) => setForm((current) => ({ ...current, reference: value }))} />
  </div><Actions busy={busy || !form.name.trim() || (requireInstallation && !form.asset_id)} cancel={cancel} label={requireInstallation ? translate('licenses.create') : translate('licenses.save')} /></form></section>
}

function Field({ label, value, onChange, type = 'text' }: { label: string; value: string; onChange: (value: string) => void; type?: string }) { return <label><span>{label}</span><input type={type} min={type === 'number' ? 1 : undefined} value={value} onChange={(event) => onChange(event.target.value)} /></label> }
function Choice({ label, value, onChange, items }: { label: string; value: string; onChange: (value: string) => void; items: Array<{ id: string; name: string }> }) { return <label><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}><option value="">{translate('licenses.none')}</option>{items.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label> }
function Actions({ busy, cancel, label }: { busy: boolean; cancel: () => void; label: string }) { return <div className="form-actions"><button type="submit" className="primary-button" disabled={busy}>{busy ? translate('common.saving') : label}</button><button type="button" className="secondary-button" onClick={cancel}>{translate('common.cancel')}</button></div> }
