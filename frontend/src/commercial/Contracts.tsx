import { useEffect, useMemo, useState } from 'react'
import { Archive, Pencil, Plus } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { FormEvent } from 'react'
import type { WorkspaceContext } from '../workspaces/api'
import type { CommercialClient, CommercialContract, ContractCost } from './api'
import { CollectionPagination } from '../CollectionPagination'

type ContractForm = {
  name: string; provider_id: string; kind: CommercialContract['kind']; status: CommercialContract['status']
  description: string; reference: string; starts_on: string; ends_on: string; renews_on: string
  auto_renew: boolean; renewal_notice_days: number
}
type CostForm = {
  label: string; amount: string; currency: string; billing_interval: ContractCost['billing_interval']
  quantity: string; starts_on: string; ends_on: string; reference: string
}

const blankContract: ContractForm = { name: '', provider_id: '', kind: 'service', status: 'draft', description: '', reference: '', starts_on: '', ends_on: '', renews_on: '', auto_renew: false, renewal_notice_days: 0 }
const blankCost: CostForm = { label: '', amount: '', currency: 'USD', billing_interval: 'monthly', quantity: '1', starts_on: '', ends_on: '', reference: '' }

function contractForm(record: CommercialContract): ContractForm {
  return { ...record, starts_on: record.starts_on ?? '', ends_on: record.ends_on ?? '', renews_on: record.renews_on ?? '' }
}

function costForm(record: ContractCost): CostForm {
  return { ...record, starts_on: record.starts_on ?? '', ends_on: record.ends_on ?? '' }
}

function dates<T extends { starts_on: string; ends_on: string }>(values: T) {
  return { ...values, starts_on: values.starts_on || null, ends_on: values.ends_on || null }
}

export function Contracts({ workspace, client }: { workspace: WorkspaceContext; client: CommercialClient }) {
  const [records, setRecords] = useState<CommercialContract[]>([])
  const [providers, setProviders] = useState<Array<{ id: string; name: string }>>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [canManage, setCanManage] = useState(false)
  const [canViewCosts, setCanViewCosts] = useState(false)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [modal, setModal] = useState<'none' | 'create' | 'edit' | 'cost' | 'edit-cost'>('none')
  const [editingCostId, setEditingCostId] = useState<string | null>(null)
  const [contract, setContract] = useState<ContractForm>(blankContract)
  const [cost, setCost] = useState<CostForm>(blankCost)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageState, setPageState] = useState({ pageSize: 50, count: 0, hasMore: false })

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([client.listContracts(workspace, query, page, controller.signal), client.providerChoices(workspace, controller.signal)])
      .then(([result, choices]) => {
        setRecords(result.results); setCanManage(result.can_manage); setCanViewCosts(result.can_view_costs)
        setPageState({ pageSize: result.page_size, count: result.count, hasMore: result.has_more })
        setProviders(choices.results); setPhase('ready')
      })
      .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client, page, query, workspace])

  const selected = useMemo(() => records.find((item) => item.id === selectedId) ?? records[0], [records, selectedId])
  function replace(record: CommercialContract) {
    setRecords((current) => current.some((item) => item.id === record.id) ? current.map((item) => item.id === record.id ? record : item) : [...current, record])
    setSelectedId(record.id); setModal('none')
  }
  async function perform(action: () => Promise<CommercialContract>) {
    setBusy(true); setError(null)
    try { replace(await action()) } catch (caught) { setError(caught instanceof Error ? caught.message : 'The contract could not be changed.') } finally { setBusy(false) }
  }
  async function archiveSelected() {
    if (!selected) return
    setBusy(true); setError(null)
    try { await client.archiveContract(workspace, selected.id); setRecords((current) => current.filter((item) => item.id !== selected.id)); setSelectedId(null) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'The contract could not be archived.') }
    finally { setBusy(false) }
  }

  return <>
    <header className="page-header"><div><h1>Services & contracts</h1></div>{canManage && <button type="button" className="primary-button" aria-label={translate('contracts.new')} title={translate('contracts.new')} onClick={() => { setContract(blankContract); setModal('create') }}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('contracts.new')}</span></button>}</header>
    <label className="search-field"><span className="sr-only">Search contracts</span><input type="search" value={query} placeholder="Search contracts, providers, or references" onChange={(event) => { setPhase('loading'); setQuery(event.target.value); setPage(1) }} /></label>
    {error && <div className="form-message error" role="alert">{error}</div>}
    {phase === 'loading' && <section className="content-section" role="status">Loading contracts…</section>}
    {phase === 'error' && <section className="content-section workspace-error" role="alert"><h2>Contracts unavailable</h2><p>The workspace commercial records could not be loaded.</p></section>}
    {phase === 'ready' && <div className="inventory-layout">
      <section className="content-section inventory-index">{records.length === 0 ? <p className="empty-state">No matching contracts have been recorded.</p> : <><ul className="inventory-list">{records.map((item) => <li key={item.id}><button type="button" className={selected?.id === item.id ? 'selected' : ''} onClick={() => setSelectedId(item.id)}><strong>{item.name}</strong><span>{item.provider_name} · {item.status}</span></button></li>)}</ul><CollectionPagination label="Contracts" page={page} pageSize={pageState.pageSize} count={pageState.count} hasMore={pageState.hasMore} onPageChange={(next) => { setPhase('loading'); setSelectedId(null); setPage(next) }} /></>}</section>
      <section className="content-section inventory-detail">{selected ? <>
        <div className="section-heading"><div><h2>{selected.name}</h2><p>{selected.provider_name} · {selected.kind}</p></div><span className="lifecycle-state">{selected.status}</span></div>
        <p>{selected.description || 'No service description recorded.'}</p>
        <dl className="inventory-provenance"><div><dt>Term</dt><dd>{selected.starts_on || 'Open'} – {selected.ends_on || 'Open'}</dd></div><div><dt>Renewal</dt><dd>{selected.renews_on || 'Not scheduled'}{selected.auto_renew ? ' · auto-renew' : ''}</dd></div><div><dt>Notice</dt><dd>{selected.renewal_notice_days ? `${selected.renewal_notice_days} days` : 'None'}</dd></div><div><dt>Reference</dt><dd>{selected.reference || 'Not recorded'}</dd></div></dl>
        {canManage && <div className="form-actions"><button type="button" className="secondary-button" onClick={() => { setContract(contractForm(selected)); setModal('edit') }}><Pencil size={15} />Edit contract</button><button type="button" className="secondary-button" disabled={busy} onClick={() => void archiveSelected()}><Archive size={15} />Archive</button></div>}
        <div className="section-heading"><h3>Costs</h3>{canManage && canViewCosts && <button type="button" className="secondary-button" onClick={() => { setCost(blankCost); setModal('cost') }}><Plus size={15} />Add cost</button>}</div>
        {!canViewCosts ? <p className="workspace-area-note">Financial terms are hidden. Your role does not include cost visibility for this workspace.</p> : selected.costs?.length ? <ul className="inventory-list">{selected.costs.map((item) => <li key={item.id}><div><strong>{item.label}</strong><span>{item.currency} {item.amount} × {item.quantity} · {item.billing_interval.replace('_', ' ')}</span></div>{canManage && <div className="form-actions"><button type="button" className="text-button" aria-label={`Edit cost ${item.label}`} onClick={() => { setCost(costForm(item)); setEditingCostId(item.id); setModal('edit-cost') }}>Edit</button><button type="button" className="text-button" aria-label={`Remove cost ${item.label}`} onClick={() => void perform(() => client.archiveCost(workspace, selected.id, item.id))}>Remove</button></div>}</li>)}</ul> : <p className="empty-state">No costs have been recorded for this contract.</p>}
      </> : <p className="empty-state">Choose a contract to inspect its terms.</p>}</section>
    </div>}
    {(modal === 'create' || modal === 'edit') && <ContractEditor title={modal === 'create' ? 'New contract' : `Edit ${selected?.name}`} value={contract} setValue={setContract} providers={providers} busy={busy} cancel={() => setModal('none')} submit={() => void perform(() => modal === 'create' ? client.createContract(workspace, { ...dates(contract), renews_on: contract.renews_on || null }) : client.updateContract(workspace, selected.id, { ...dates(contract), renews_on: contract.renews_on || null }))} />}
    {(modal === 'cost' || modal === 'edit-cost') && selected && <CostEditor title={modal === 'cost' ? 'Add contract cost' : 'Edit contract cost'} submitLabel={modal === 'cost' ? 'Add cost' : 'Save cost'} value={cost} setValue={setCost} busy={busy} cancel={() => setModal('none')} submit={() => void perform(() => modal === 'cost' ? client.createCost(workspace, selected.id, dates(cost)) : client.updateCost(workspace, selected.id, editingCostId as string, dates(cost)))} />}
  </>
}

function ContractEditor({ title, value, setValue, providers, busy, cancel, submit }: { title: string; value: ContractForm; setValue: (value: ContractForm) => void; providers: Array<{ id: string; name: string }>; busy: boolean; cancel: () => void; submit: () => void }) {
  function save(event: FormEvent) { event.preventDefault(); submit() }
  return <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="contract-editor-title"><form className="record-form" onSubmit={save}><div className="section-heading"><h2 id="contract-editor-title">{title}</h2></div><p className="workspace-area-note">Contract details are operational fields. Keep pricing, rates, and other financial terms in Costs so their separate access policy applies.</p><div className="form-grid">
    <Field label="Contract name" value={value.name} onChange={(name) => setValue({ ...value, name })} />
    <label><span>Provider</span><select required value={value.provider_id} onChange={(event) => setValue({ ...value, provider_id: event.target.value })}><option value="">Choose provider</option>{providers.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
    <Choice label="Kind" value={value.kind} items={['service', 'support', 'lease', 'subscription', 'other']} onChange={(kind) => setValue({ ...value, kind: kind as CommercialContract['kind'] })} />
    <Choice label="Status" value={value.status} items={['draft', 'active', 'expired', 'terminated']} onChange={(status) => setValue({ ...value, status: status as CommercialContract['status'] })} />
    <Field label="Starts on" type="date" value={value.starts_on} onChange={(starts_on) => setValue({ ...value, starts_on })} /><Field label="Ends on" type="date" value={value.ends_on} onChange={(ends_on) => setValue({ ...value, ends_on })} />
    <Field label="Renews on" type="date" value={value.renews_on} onChange={(renews_on) => setValue({ ...value, renews_on })} /><Field label="Renewal notice days" type="number" value={String(value.renewal_notice_days)} onChange={(renewal_notice_days) => setValue({ ...value, renewal_notice_days: Number(renewal_notice_days) })} />
    <Field label="Reference" value={value.reference} onChange={(reference) => setValue({ ...value, reference })} /><Field label="Description" value={value.description} onChange={(description) => setValue({ ...value, description })} />
    <label className="checkbox-field"><input type="checkbox" checked={value.auto_renew} onChange={(event) => setValue({ ...value, auto_renew: event.target.checked })} /><span>Auto-renew</span></label>
  </div><Actions busy={busy || !value.name.trim() || !value.provider_id} cancel={cancel} label="Save contract" /></form></section>
}

function CostEditor({ title, submitLabel, value, setValue, busy, cancel, submit }: { title: string; submitLabel: string; value: CostForm; setValue: (value: CostForm) => void; busy: boolean; cancel: () => void; submit: () => void }) {
  function save(event: FormEvent) { event.preventDefault(); submit() }
  return <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="cost-editor-title"><form className="record-form" onSubmit={save}><div className="section-heading"><h2 id="cost-editor-title">{title}</h2></div><div className="form-grid">
    <Field label="Cost label" value={value.label} onChange={(label) => setValue({ ...value, label })} /><Field label="Amount" type="number" step="0.01" value={value.amount} onChange={(amount) => setValue({ ...value, amount })} />
    <Field label="Currency" value={value.currency} onChange={(currency) => setValue({ ...value, currency })} /><Choice label="Billing interval" value={value.billing_interval} items={['one_time', 'monthly', 'quarterly', 'annual']} onChange={(billing_interval) => setValue({ ...value, billing_interval: billing_interval as ContractCost['billing_interval'] })} />
    <Field label="Quantity" type="number" step="0.001" value={value.quantity} onChange={(quantity) => setValue({ ...value, quantity })} /><Field label="Reference" value={value.reference} onChange={(reference) => setValue({ ...value, reference })} />
    <Field label="Starts on" type="date" value={value.starts_on} onChange={(starts_on) => setValue({ ...value, starts_on })} /><Field label="Ends on" type="date" value={value.ends_on} onChange={(ends_on) => setValue({ ...value, ends_on })} />
  </div><Actions busy={busy || !value.label.trim() || !value.amount || !value.currency} cancel={cancel} label={submitLabel} /></form></section>
}

function Field({ label, value, onChange, type = 'text', step }: { label: string; value: string; onChange: (value: string) => void; type?: string; step?: string }) { return <label><span>{label}</span><input required={label === 'Contract name' || label === 'Cost label'} type={type} step={step} min={type === 'number' ? 0 : undefined} value={value} onChange={(event) => onChange(event.target.value)} /></label> }
function Choice({ label, value, items, onChange }: { label: string; value: string; items: string[]; onChange: (value: string) => void }) { return <label><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}>{items.map((item) => <option value={item} key={item}>{item.replace('_', ' ')}</option>)}</select></label> }
function Actions({ busy, cancel, label }: { busy: boolean; cancel: () => void; label: string }) { return <div className="form-actions"><button type="submit" className="primary-button" disabled={busy}>{busy ? 'Saving…' : label}</button><button type="button" className="secondary-button" onClick={cancel}>Cancel</button></div> }
