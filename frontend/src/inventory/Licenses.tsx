import { useEffect, useMemo, useState } from 'react'
import { Pencil, Plus, UserPlus, X } from 'lucide-react'
import type { Dispatch, FormEvent, SetStateAction } from 'react'
import type { InventoryClient, SoftwareChoices, SoftwareLicense } from './api'
import type { WorkspaceContext } from '../workspaces/api'
import { CollectionPagination } from '../CollectionPagination'

type LicenseMode = 'read' | 'create' | 'edit' | 'seat' | 'link'
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

const blank: LicenseFormState = {
  name: '', asset_id: '', kind: 'subscription', status: 'active', seat_limit: 1,
  starts_on: '', renews_on: '', ends_on: '', renewal_interval: 'annual', auto_renew: true, reference: '',
}

function formFromLicense(record: SoftwareLicense): LicenseFormState {
  return {
    name: record.name,
    asset_id: '',
    kind: record.kind,
    status: record.status,
    seat_limit: record.seat_limit,
    starts_on: record.starts_on ?? '',
    renews_on: record.renews_on ?? '',
    ends_on: record.ends_on ?? '',
    renewal_interval: record.renewal_interval,
    auto_renew: record.auto_renew,
    reference: record.reference,
  }
}

function payloadFromForm(form: LicenseFormState) {
  const perpetual = form.kind === 'perpetual'
  return {
    ...form,
    seat_limit: Number(form.seat_limit),
    starts_on: form.starts_on || null,
    renews_on: form.renews_on || null,
    ends_on: form.ends_on || null,
    renewal_interval: perpetual ? 'none' : form.renewal_interval,
    auto_renew: perpetual ? false : form.auto_renew,
  }
}

function updatePayloadFromForm(form: LicenseFormState) {
  const payload = payloadFromForm(form)
  return {
    name: payload.name,
    kind: payload.kind,
    status: payload.status,
    seat_limit: payload.seat_limit,
    starts_on: payload.starts_on,
    renews_on: payload.renews_on,
    ends_on: payload.ends_on,
    renewal_interval: payload.renewal_interval,
    auto_renew: payload.auto_renew,
    reference: payload.reference,
  }
}

export function Licenses({ workspace, client }: { workspace: WorkspaceContext; client: InventoryClient }) {
  const [records, setRecords] = useState<SoftwareLicense[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [choices, setChoices] = useState<SoftwareChoices>({ installations: [], people: [] })
  const [canManage, setCanManage] = useState(false)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [mode, setMode] = useState<LicenseMode>('read')
  const [form, setForm] = useState<LicenseFormState>(blank)
  const [seat, setSeat] = useState<SeatFormState>({ person_id: '', installation_id: '' })
  const [linkId, setLinkId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageState, setPageState] = useState({ pageSize: 50, count: 0, hasMore: false })

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([client.listLicenses(workspace, page, controller.signal), client.softwareChoices(workspace)])
      .then(([result, available]) => {
        setRecords(result.results)
        setCanManage(result.can_manage)
        setPageState({ pageSize: result.page_size, count: result.count, hasMore: result.has_more })
        setChoices(available)
        setPhase('ready')
      })
      .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client, page, workspace])

  const selected = useMemo(
    () => records.find((record) => record.id === selectedId) ?? records[0],
    [records, selectedId],
  )

  function replace(record: SoftwareLicense) {
    setRecords((current) => current.some((item) => item.id === record.id)
      ? current.map((item) => item.id === record.id ? record : item)
      : [...current, record])
    setSelectedId(record.id)
    setMode('read')
    setSeat({ person_id: '', installation_id: '' })
    setLinkId('')
  }

  async function perform(action: () => Promise<SoftwareLicense>) {
    setBusy(true)
    setError(null)
    try {
      replace(await action())
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The license could not be changed.')
    } finally {
      setBusy(false)
    }
  }

  return <>
    <header className="page-header">
      <div><h1>Licenses</h1><p>{workspace.kind === 'msp' ? 'MSP' : 'Client'} software entitlements, covered installations, seats, and renewal dates.</p></div>
      {canManage && <button type="button" className="primary-button" onClick={() => { setForm(blank); setMode('create') }}><Plus size={16} />New license</button>}
    </header>
    {error && <div className="form-message error" role="alert">{error}</div>}
    {phase === 'loading' && <section className="content-section" role="status">Loading software licenses…</section>}
    {phase === 'error' && <section className="content-section workspace-error" role="alert"><h2>Licenses unavailable</h2><p>The workspace license inventory could not be loaded.</p></section>}
    {phase === 'ready' && <div className="inventory-layout">
      <section className="content-section inventory-index">
        {records.length === 0 ? <p className="empty-state">No software licenses have been recorded.</p> : <><ul className="inventory-list">{records.map((record) => <li key={record.id}><button type="button" className={selected?.id === record.id ? 'selected' : ''} onClick={() => { setSelectedId(record.id); setMode('read') }}><strong>{record.name}</strong><span>{record.product_name} · {record.active_seats}/{record.seat_limit} seats</span></button></li>)}</ul><CollectionPagination label="Licenses" page={page} pageSize={pageState.pageSize} count={pageState.count} hasMore={pageState.hasMore} onPageChange={(next) => { setPhase('loading'); setSelectedId(null); setMode('read'); setPage(next) }} /></>}
      </section>
      <section className="content-section inventory-detail">
        {selected ? <LicenseDetail record={selected} canManage={canManage} choices={choices} mode={mode} setMode={setMode} seat={seat} setSeat={setSeat} linkId={linkId} setLinkId={setLinkId} busy={busy} perform={perform} client={client} workspace={workspace} beginEdit={() => { setForm(formFromLicense(selected)); setMode('edit') }} /> : <p className="empty-state">Choose a license to inspect its entitlement.</p>}
      </section>
    </div>}
    {mode === 'create' && <LicenseForm title="New software license" form={form} setForm={setForm} choices={choices} busy={busy} requireInstallation cancel={() => setMode('read')} submit={() => void perform(() => client.createLicense(workspace, payloadFromForm(form)))} />}
    {mode === 'edit' && selected && <LicenseForm title={`Edit ${selected.name}`} form={form} setForm={setForm} choices={choices} busy={busy} cancel={() => setMode('read')} submit={() => void perform(() => client.updateLicense(workspace, selected.id, updatePayloadFromForm(form)))} />}
  </>
}

type LicenseDetailProps = {
  record: SoftwareLicense
  canManage: boolean
  choices: SoftwareChoices
  mode: LicenseMode
  setMode: Dispatch<SetStateAction<LicenseMode>>
  seat: SeatFormState
  setSeat: Dispatch<SetStateAction<SeatFormState>>
  linkId: string
  setLinkId: Dispatch<SetStateAction<string>>
  busy: boolean
  perform: (action: () => Promise<SoftwareLicense>) => Promise<void>
  client: InventoryClient
  workspace: WorkspaceContext
  beginEdit: () => void
}

function LicenseDetail({ record, canManage, choices, mode, setMode, seat, setSeat, linkId, setLinkId, busy, perform, client, workspace, beginEdit }: LicenseDetailProps) {
  const activeSeats = record.seats.filter((item) => !item.revoked_at)
  const linked = new Set(record.installations.map((item) => item.id))
  const availableInstallations = choices.installations
    .filter((item) => item.product_id === record.product_id && !linked.has(item.id))
    .map((item) => ({ id: item.id, name: item.asset_name ?? item.id }))
  return <>
    <div className="section-heading"><div><h2>{record.name}</h2><p>{record.supplier_name} / {record.product_name}{record.model_name ? ` / ${record.model_name}` : ''}</p></div><span className="lifecycle-state">{record.status}</span></div>
    <dl className="inventory-provenance"><div><dt>License</dt><dd>{record.kind}</dd></div><div><dt>Seats</dt><dd>{record.active_seats} assigned · {record.seat_limit} total</dd></div><div><dt>Renewal</dt><dd>{record.renews_on || 'Not scheduled'}{record.auto_renew ? ' · auto-renew' : ''}</dd></div><div><dt>Term</dt><dd>{record.starts_on || 'Open'} – {record.ends_on || 'Open'}</dd></div><div><dt>Reference</dt><dd>{record.reference || 'Not recorded'}</dd></div></dl>
    {canManage && mode === 'read' && <div className="form-actions"><button type="button" className="secondary-button" onClick={beginEdit}><Pencil size={15} />Edit license</button><button type="button" className="secondary-button" onClick={() => setMode('seat')}><UserPlus size={15} />Assign seat</button><button type="button" className="secondary-button" onClick={() => setMode('link')}>Link installation</button></div>}
    {mode === 'seat' && <form className="hardware-form" onSubmit={(event) => { event.preventDefault(); void perform(() => client.assignLicenseSeat(workspace, record.id, { person_id: seat.person_id || null, installation_id: seat.installation_id || null })) }}><h3>Assign seat</h3><div className="field-grid"><Choice label="Person" value={seat.person_id} onChange={(value) => setSeat((current) => ({ ...current, person_id: value }))} items={choices.people} /><Choice label="Installation" value={seat.installation_id} onChange={(value) => setSeat((current) => ({ ...current, installation_id: value }))} items={record.installations} /></div><Actions busy={busy || (!seat.person_id && !seat.installation_id)} cancel={() => setMode('read')} label="Assign seat" /></form>}
    {mode === 'link' && <form className="hardware-form" onSubmit={(event) => { event.preventDefault(); void perform(() => client.linkLicenseInstallation(workspace, record.id, linkId)) }}><h3>Link installation</h3><Choice label="Software installation" value={linkId} onChange={setLinkId} items={availableInstallations} /><Actions busy={busy || !linkId} cancel={() => setMode('read')} label="Link installation" /></form>}
    <section className="license-section"><h3>Seat assignments</h3>{activeSeats.length === 0 ? <p className="empty-state">No seats are assigned.</p> : <ul className="license-seat-list">{activeSeats.map((item) => <li key={item.id}><div><strong>Seat {item.seat_number}</strong><span>{[item.person_name, item.installation_name].filter(Boolean).join(' · ')}</span></div>{canManage && <button type="button" className="icon-button" aria-label={`Revoke seat ${item.seat_number}`} onClick={() => void perform(() => client.revokeLicenseSeat(workspace, record.id, item.id))}><X size={15} /></button>}</li>)}</ul>}</section>
    <section className="lifecycle-history"><h3>License history</h3><ol>{record.events.map((item) => <li key={item.id}><strong>{item.event_type.replaceAll('_', ' ')}</strong><span>{[item.person_name, item.installation_name, item.seat_number ? `seat ${item.seat_number}` : ''].filter(Boolean).join(' · ')}</span><time dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleString()}</time></li>)}</ol></section>
  </>
}

type LicenseFormProps = {
  title: string
  form: LicenseFormState
  setForm: Dispatch<SetStateAction<LicenseFormState>>
  choices: SoftwareChoices
  busy: boolean
  requireInstallation?: boolean
  cancel: () => void
  submit: () => void
}

function LicenseForm({ title, form, setForm, choices, busy, requireInstallation = false, cancel, submit }: LicenseFormProps) {
  function handleSubmit(event: FormEvent) { event.preventDefault(); submit() }
  return <section className="content-section inventory-create"><h2>{title}</h2><form className="hardware-form" onSubmit={handleSubmit}><div className="field-grid">
    <Field label="License name" value={form.name} onChange={(value) => setForm((current) => ({ ...current, name: value }))} />
    {requireInstallation && <Choice label="Initial software installation" value={form.asset_id} onChange={(value) => setForm((current) => ({ ...current, asset_id: value }))} items={choices.installations.map((item) => ({ id: item.asset_id ?? '', name: `${item.asset_name ?? 'Software asset'} · ${item.product_name ?? 'Unknown product'}` })).filter((item) => item.id)} />}
    <label><span>License kind</span><select value={form.kind} onChange={(event) => setForm((current) => ({ ...current, kind: event.target.value as SoftwareLicense['kind'] }))}>{['subscription', 'perpetual', 'trial'].map((item) => <option key={item}>{item}</option>)}</select></label>
    {!requireInstallation && <label><span>Status</span><select value={form.status} onChange={(event) => setForm((current) => ({ ...current, status: event.target.value as SoftwareLicense['status'] }))}>{['active', 'suspended', 'expired', 'terminated'].map((item) => <option key={item}>{item}</option>)}</select></label>}
    <Field label="Seat limit" type="number" value={String(form.seat_limit)} onChange={(value) => setForm((current) => ({ ...current, seat_limit: Number(value) }))} />
    <Field label="Starts on" type="date" value={form.starts_on} onChange={(value) => setForm((current) => ({ ...current, starts_on: value }))} />
    <Field label="Renews on" type="date" value={form.renews_on} onChange={(value) => setForm((current) => ({ ...current, renews_on: value }))} />
    <Field label="Ends on" type="date" value={form.ends_on} onChange={(value) => setForm((current) => ({ ...current, ends_on: value }))} />
    <label><span>Renewal interval</span><select value={form.renewal_interval} disabled={form.kind === 'perpetual'} onChange={(event) => setForm((current) => ({ ...current, renewal_interval: event.target.value as SoftwareLicense['renewal_interval'] }))}>{['none', 'monthly', 'annual', 'multi_year'].map((item) => <option key={item}>{item.replace('_', ' ')}</option>)}</select></label>
    <label className="checkbox-field"><input type="checkbox" checked={form.auto_renew} disabled={form.kind === 'perpetual'} onChange={(event) => setForm((current) => ({ ...current, auto_renew: event.target.checked }))} /><span>Auto-renew</span></label>
    <Field label="Reference" value={form.reference} onChange={(value) => setForm((current) => ({ ...current, reference: value }))} />
  </div><Actions busy={busy || !form.name.trim() || (requireInstallation && !form.asset_id)} cancel={cancel} label={requireInstallation ? 'Create license' : 'Save license'} /></form></section>
}

function Field({ label, value, onChange, type = 'text' }: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  return <label><span>{label}</span><input type={type} min={type === 'number' ? 1 : undefined} value={value} onChange={(event) => onChange(event.target.value)} /></label>
}

function Choice({ label, value, onChange, items }: { label: string; value: string; onChange: (value: string) => void; items: Array<{ id: string; name: string }> }) {
  return <label><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}><option value="">None</option>{items.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
}

function Actions({ busy, cancel, label }: { busy: boolean; cancel: () => void; label: string }) {
  return <div className="form-actions"><button type="submit" className="primary-button" disabled={busy}>{busy ? 'Saving…' : label}</button><button type="button" className="secondary-button" onClick={cancel}>Cancel</button></div>
}
