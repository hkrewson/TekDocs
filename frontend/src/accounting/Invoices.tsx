import { useEffect, useMemo, useState } from 'react'
import { FileCheck2, Pencil, Plus, Settings, Trash2 } from 'lucide-react'
import type { FormEvent } from 'react'
import { formatPlainDate, translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { InvoiceClient, InvoiceDraft, InvoiceIssueSettings, InvoiceLine, InvoiceOrigin, TaxRateChoice } from './api'

type DraftForm = { currency: string; invoice_date: string; due_date: string; reference: string; notes: string }
type LineForm = {
  originKey: string
  description: string
  quantity: string
  unit_amount: string
  tax_rate_id: string
  tax_rate_name: string
  tax_rate_value: string
  tax_inclusive: boolean
}

function isoDate(offsetDays = 0) {
  const value = new Date()
  value.setDate(value.getDate() + offsetDays)
  return value.toISOString().slice(0, 10)
}

const emptyDraft = (): DraftForm => ({
  currency: 'USD',
  invoice_date: isoDate(),
  due_date: isoDate(30),
  reference: '',
  notes: '',
})
const emptyLine = (): LineForm => ({ originKey: '', description: '', quantity: '1.000', unit_amount: '', tax_rate_id: '', tax_rate_name: '', tax_rate_value: '0', tax_inclusive: false })

function draftForm(record: InvoiceDraft): DraftForm {
  return {
    currency: record.currency,
    invoice_date: record.invoice_date,
    due_date: record.due_date,
    reference: record.reference,
    notes: record.notes,
  }
}

function lineForm(record: InvoiceLine): LineForm {
  return {
    originKey: '',
    description: record.description,
    quantity: record.quantity,
    unit_amount: record.unit_amount,
    tax_rate_id: record.tax_rate_name ? '__snapshot__' : '',
    tax_rate_name: record.tax_rate_name,
    tax_rate_value: record.tax_rate_value,
    tax_inclusive: record.tax_inclusive,
  }
}

function originLabel(origin: InvoiceOrigin) {
  const labels = {
    catalog_product: translate('accounting.originProduct'),
    service_rate: translate('accounting.originService'),
    contract_cost: translate('accounting.originContract'),
  }
  return `${labels[origin.origin_type]} · ${origin.name} · ${origin.currency} ${origin.unit_amount}`
}

export function Invoices({ workspace, client }: { workspace: WorkspaceContext; client: InvoiceClient }) {
  const [records, setRecords] = useState<InvoiceDraft[]>([])
  const [origins, setOrigins] = useState<InvoiceOrigin[]>([])
  const [taxRates, setTaxRates] = useState<TaxRateChoice[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [canManage, setCanManage] = useState(false)
  const [canIssue, setCanIssue] = useState(false)
  const [issueSettings, setIssueSettings] = useState<InvoiceIssueSettings | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [editor, setEditor] = useState<'none' | 'new' | 'draft' | 'line' | 'issue-settings'>('none')
  const [editingLineId, setEditingLineId] = useState<string | null>(null)
  const [draft, setDraft] = useState<DraftForm>(emptyDraft)
  const [line, setLine] = useState<LineForm>(emptyLine)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    client.list(workspace, controller.signal)
      .then(async (result) => {
        const [choices, settings] = await Promise.all([
          result.can_manage ? client.choices(workspace, controller.signal) : Promise.resolve({ origins: [], tax_rates: [] }),
          result.can_issue ? client.issueSettings(workspace, controller.signal) : Promise.resolve(null),
        ])
        setRecords(result.results)
        setCanManage(result.can_manage)
        setCanIssue(result.can_issue)
        setIssueSettings(settings)
        setOrigins(choices.origins)
        setTaxRates(choices.tax_rates)
        setPhase('ready')
      })
      .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client, workspace])

  const selected = useMemo(
    () => records.find((record) => record.id === selectedId) ?? records[0],
    [records, selectedId],
  )

  function replace(record: InvoiceDraft) {
    setRecords((current) => current.some((item) => item.id === record.id)
      ? current.map((item) => item.id === record.id ? record : item)
      : [record, ...current])
    setSelectedId(record.id)
    setEditor('none')
    setEditingLineId(null)
  }

  async function perform(action: () => Promise<InvoiceDraft>) {
    setBusy(true)
    setError(null)
    try { replace(await action()) }
    catch (caught) { setError(caught instanceof Error ? caught.message : translate('accounting.changeFailed')) }
    finally { setBusy(false) }
  }

  async function removeDraft() {
    if (!selected || !window.confirm(translate('accounting.deleteDraftConfirm'))) return
    setBusy(true)
    setError(null)
    try {
      await client.remove(workspace, selected.id)
      setRecords((current) => current.filter((record) => record.id !== selected.id))
      setSelectedId(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate('accounting.deleteFailed'))
    } finally { setBusy(false) }
  }

  function beginLine(record?: InvoiceLine) {
    setEditingLineId(record?.id ?? null)
    setLine(record ? lineForm(record) : emptyLine())
    setEditor('line')
  }

  async function issueSelected() {
    if (!selected) return
    if (!issueSettings?.issue_ready) {
      setEditor('issue-settings')
      return
    }
    if (!window.confirm(translate('accounting.issueConfirm'))) return
    await perform(() => client.issue(workspace, selected.id))
  }

  async function saveIssueSettings(value: InvoiceIssueSettings) {
    setBusy(true)
    setError(null)
    try {
      const payload: Record<string, unknown> = { ...value }
      delete payload.configured
      delete payload.issue_ready
      setIssueSettings(await client.saveIssueSettings(workspace, payload))
      setEditor('none')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate('accounting.settingsFailed'))
    } finally { setBusy(false) }
  }

  return <>
    <header className="page-header">
      <div><h1>{translate('accounting.heading')}</h1></div>
      <div className="form-actions">
        {canIssue && <button type="button" className="secondary-button" onClick={() => setEditor('issue-settings')}><Settings size={16} aria-hidden="true" />{translate('accounting.issueSettings')}</button>}
        {canManage && <button type="button" className="primary-button" aria-label={translate('accounting.newDraft')} onClick={() => { setDraft(emptyDraft()); setEditor('new') }}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('accounting.newDraft')}</span></button>}
      </div>
    </header>
    {error && <div className="form-message error" role="alert">{error}</div>}
    {phase === 'loading' && <section className="content-section" role="status">{translate('accounting.loading')}</section>}
    {phase === 'error' && <section className="content-section workspace-error" role="alert"><h2>{translate('accounting.unavailable')}</h2><p>{translate('accounting.loadFailed')}</p></section>}
    {phase === 'ready' && <div className="inventory-layout">
      <section className="content-section inventory-index">
        {records.length === 0 ? <p className="empty-state">{translate('accounting.empty')}</p> : <ul className="inventory-list">{records.map((record) => <li key={record.id}><button type="button" className={selected?.id === record.id ? 'selected' : ''} onClick={() => setSelectedId(record.id)}><strong>{record.number || formatPlainDate(record.invoice_date)}</strong><span>{record.state === 'draft' ? translate('accounting.draft') : translate('accounting.issued')} · {record.currency} {record.total}</span></button></li>)}</ul>}
      </section>
      <section className="content-section inventory-detail">
        {selected ? <>
          <div className="section-heading"><div><h2>{selected.number || `${translate('accounting.draft')} · ${formatPlainDate(selected.invoice_date)}`}</h2><p>{selected.reference || workspace.name}</p></div><span className="lifecycle-state">{selected.state}</span></div>
          <dl className="inventory-provenance">
            <div><dt>{translate('accounting.invoiceDate')}</dt><dd>{formatPlainDate(selected.invoice_date)}</dd></div>
            <div><dt>{translate('accounting.dueDate')}</dt><dd>{formatPlainDate(selected.due_date)}</dd></div>
            <div><dt>{translate('accounting.currency')}</dt><dd>{selected.currency}</dd></div>
            <div><dt>{translate('accounting.reference')}</dt><dd>{selected.reference || '—'}</dd></div>
          </dl>
          {selected.notes && <p>{selected.notes}</p>}
          {selected.state === 'draft' && <div className="form-actions">{canManage && <><button type="button" className="secondary-button" onClick={() => { setDraft(draftForm(selected)); setEditor('draft') }}><Pencil size={15} />{translate('accounting.editDraft')}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => { void removeDraft() }}><Trash2 size={15} />{translate('accounting.deleteDraft')}</button></>}{canIssue && <button type="button" className="primary-button" disabled={busy || selected.lines.length === 0} onClick={() => { void issueSelected() }}><FileCheck2 size={15} />{translate('accounting.issue')}</button>}</div>}
          {selected.state === 'issued' && selected.issued_at && <p className="workspace-area-note">{translate('accounting.issuedProof', { date: formatPlainDate(selected.issued_at.slice(0, 10)), fingerprint: selected.key_fingerprint?.slice(0, 12) ?? '' })}</p>}
          <div className="section-heading"><h3>{translate('accounting.lines')}</h3>{canManage && selected.state === 'draft' && <button type="button" className="secondary-button" onClick={() => beginLine()}><Plus size={15} />{translate('accounting.addLine')}</button>}</div>
          {selected.lines.length === 0 ? <p className="empty-state">{translate('accounting.noLines')}</p> : <ul className="inventory-list">{selected.lines.map((item) => <li key={item.id}><div><strong>{item.description}</strong><span>{item.quantity} × {item.currency} {item.unit_amount}{item.tax_rate_name ? ` · ${item.tax_rate_name}` : ''}</span></div><div><strong>{item.currency} {item.total}</strong>{canManage && selected.state === 'draft' && <div className="form-actions"><button type="button" className="text-button" aria-label={translate('accounting.editLine', { description: item.description })} onClick={() => beginLine(item)}>{translate('common.edit')}</button><button type="button" className="text-button" aria-label={translate('accounting.deleteLine', { description: item.description })} onClick={() => { void perform(() => client.removeLine(workspace, selected.id, item.id)) }}>{translate('common.remove')}</button></div>}</div></li>)}</ul>}
          <dl className="inventory-provenance">
            <div><dt>{translate('accounting.subtotal')}</dt><dd>{selected.currency} {selected.subtotal}</dd></div>
            <div><dt>{translate('accounting.tax')}</dt><dd>{selected.currency} {selected.tax_total}</dd></div>
            <div><dt>{translate('accounting.total')}</dt><dd><strong>{selected.currency} {selected.total}</strong></dd></div>
          </dl>
        </> : <p className="empty-state">{translate('accounting.choose')}</p>}
      </section>
    </div>}
    {(editor === 'new' || editor === 'draft') && <DraftEditor value={draft} setValue={setDraft} busy={busy} title={editor === 'new' ? translate('accounting.newDraftTitle') : translate('accounting.editDraftTitle')} cancel={() => setEditor('none')} submit={() => { void perform(() => editor === 'new' ? client.create(workspace, draft) : client.update(workspace, selected.id, draft)) }} />}
    {editor === 'line' && selected && <LineEditor value={line} setValue={setLine} origins={origins.filter((origin) => origin.currency === selected.currency)} taxRates={taxRates} busy={busy} cancel={() => setEditor('none')} submit={() => { const [origin_type, origin_id] = line.originKey.split(':'); const selectedTax = taxRates.find((rate) => rate.id === line.tax_rate_id); const values = editingLineId ? { description: line.description, quantity: line.quantity, unit_amount: line.unit_amount, tax_rate_name: selectedTax?.name ?? line.tax_rate_name, tax_rate_value: selectedTax?.rate ?? line.tax_rate_value, tax_inclusive: selectedTax?.inclusive ?? line.tax_inclusive } : line.originKey ? { origin_type, origin_id, tax_rate_id: line.tax_rate_id || null } : { description: line.description, quantity: line.quantity, unit_amount: line.unit_amount, tax_rate_id: line.tax_rate_id || null }; void perform(() => editingLineId ? client.updateLine(workspace, selected.id, editingLineId, values) : client.addLine(workspace, selected.id, values)) }} />}
    {editor === 'issue-settings' && issueSettings && <IssueSettingsEditor initial={issueSettings} busy={busy} cancel={() => setEditor('none')} submit={(value) => { void saveIssueSettings(value) }} />}
  </>
}

function IssueSettingsEditor({ initial, busy, cancel, submit }: { initial: InvoiceIssueSettings; busy: boolean; cancel: () => void; submit: (value: InvoiceIssueSettings) => void }) {
  const [value, setValue] = useState(initial)
  function save(event: FormEvent) { event.preventDefault(); submit(value) }
  return <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="invoice-issue-settings-title"><form className="record-form" onSubmit={save}><div className="section-heading"><h2 id="invoice-issue-settings-title">{translate('accounting.issueSettings')}</h2></div><div className="form-grid">
    <Field label={translate('accounting.legalName')} value={value.legal_name} onChange={(legal_name) => setValue({ ...value, legal_name })} />
    <Field label={translate('accounting.billingEmail')} type="email" value={value.billing_email} onChange={(billing_email) => setValue({ ...value, billing_email })} />
    <Field label={translate('accounting.addressLine1')} value={value.address_line_1} onChange={(address_line_1) => setValue({ ...value, address_line_1 })} />
    <Field label={translate('accounting.addressLine2')} value={value.address_line_2} required={false} onChange={(address_line_2) => setValue({ ...value, address_line_2 })} />
    <Field label={translate('accounting.city')} value={value.city} onChange={(city) => setValue({ ...value, city })} />
    <Field label={translate('accounting.region')} value={value.region} required={false} onChange={(region) => setValue({ ...value, region })} />
    <Field label={translate('accounting.postalCode')} value={value.postal_code} onChange={(postal_code) => setValue({ ...value, postal_code })} />
    <Field label={translate('accounting.countryCode')} value={value.country_code} onChange={(country_code) => setValue({ ...value, country_code: country_code.toUpperCase() })} />
    <Field label={translate('accounting.defaultCurrency')} value={value.default_currency} onChange={(default_currency) => setValue({ ...value, default_currency: default_currency.toUpperCase() })} />
    <Field label={translate('accounting.paymentTerms')} type="number" value={String(value.payment_terms_days)} onChange={(payment_terms_days) => setValue({ ...value, payment_terms_days: Number(payment_terms_days) })} />
    <Field label={translate('accounting.invoicePrefix')} value={value.invoice_prefix} onChange={(invoice_prefix) => setValue({ ...value, invoice_prefix: invoice_prefix.toUpperCase() })} />
    <label><span>{translate('accounting.yearlyReset')}</span><input type="checkbox" checked={value.yearly_reset} onChange={(event) => setValue({ ...value, yearly_reset: event.target.checked })} /></label>
  </div><Actions busy={busy} cancel={cancel} label={translate('accounting.saveSettings')} /></form></section>
}

function DraftEditor({ value, setValue, busy, title, cancel, submit }: { value: DraftForm; setValue: (value: DraftForm) => void; busy: boolean; title: string; cancel: () => void; submit: () => void }) {
  function save(event: FormEvent) { event.preventDefault(); submit() }
  return <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="invoice-editor-title"><form className="record-form" onSubmit={save}><div className="section-heading"><h2 id="invoice-editor-title">{title}</h2></div><div className="form-grid">
    <Field label={translate('accounting.invoiceDate')} type="date" value={value.invoice_date} onChange={(invoice_date) => setValue({ ...value, invoice_date })} />
    <Field label={translate('accounting.dueDate')} type="date" value={value.due_date} onChange={(due_date) => setValue({ ...value, due_date })} />
    <Field label={translate('accounting.currency')} value={value.currency} onChange={(currency) => setValue({ ...value, currency: currency.toUpperCase() })} />
    <Field label={translate('accounting.reference')} value={value.reference} required={false} onChange={(reference) => setValue({ ...value, reference })} />
    <label className="wide-field"><span>{translate('accounting.notes')}</span><textarea rows={3} value={value.notes} onChange={(event) => setValue({ ...value, notes: event.target.value })} /></label>
  </div><Actions busy={busy} cancel={cancel} label={translate('accounting.saveDraft')} /></form></section>
}

function LineEditor({ value, setValue, origins, taxRates, busy, cancel, submit }: { value: LineForm; setValue: (value: LineForm) => void; origins: InvoiceOrigin[]; taxRates: TaxRateChoice[]; busy: boolean; cancel: () => void; submit: () => void }) {
  function save(event: FormEvent) { event.preventDefault(); submit() }
  return <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="invoice-line-editor-title"><form className="record-form" onSubmit={save}><div className="section-heading"><h2 id="invoice-line-editor-title">{translate('accounting.lineTitle')}</h2></div><div className="form-grid">
    <label className="wide-field"><span>{translate('accounting.origin')}</span><select value={value.originKey} onChange={(event) => { const origin = origins.find((item) => `${item.origin_type}:${item.id}` === event.target.value); setValue(origin ? { ...value, originKey: event.target.value, description: origin.name, quantity: origin.quantity, unit_amount: origin.unit_amount } : { ...value, originKey: '' }) }}><option value="">{translate('accounting.manualLine')}</option>{origins.map((origin) => <option key={`${origin.origin_type}:${origin.id}`} value={`${origin.origin_type}:${origin.id}`}>{originLabel(origin)}</option>)}</select></label>
    <Field label={translate('accounting.description')} value={value.description} disabled={Boolean(value.originKey)} onChange={(description) => setValue({ ...value, description })} />
    <Field label={translate('accounting.quantity')} type="number" step="0.001" value={value.quantity} disabled={Boolean(value.originKey)} onChange={(quantity) => setValue({ ...value, quantity })} />
    <Field label={translate('accounting.unitAmount')} type="number" step="0.0001" value={value.unit_amount} disabled={Boolean(value.originKey)} onChange={(unit_amount) => setValue({ ...value, unit_amount })} />
    <label><span>{translate('accounting.taxRate')}</span><select value={value.tax_rate_id} onChange={(event) => setValue(event.target.value ? { ...value, tax_rate_id: event.target.value } : { ...value, tax_rate_id: '', tax_rate_name: '', tax_rate_value: '0', tax_inclusive: false })}><option value="">{translate('accounting.noTax')}</option>{value.tax_rate_id === '__snapshot__' && <option value="__snapshot__">{value.tax_rate_name} · {value.tax_rate_value}</option>}{taxRates.map((rate) => <option key={rate.id} value={rate.id}>{rate.name} · {rate.rate}{rate.inclusive ? ' · inclusive' : ''}</option>)}</select></label>
  </div><Actions busy={busy || (!value.originKey && (!value.description.trim() || !value.unit_amount))} cancel={cancel} label={translate('accounting.saveLine')} /></form></section>
}

function Field({ label, value, onChange, type = 'text', step, disabled = false, required = true }: { label: string; value: string; onChange: (value: string) => void; type?: string; step?: string; disabled?: boolean; required?: boolean }) {
  return <label><span>{label}</span><input required={required} disabled={disabled} type={type} step={step} min={type === 'number' ? 0 : undefined} value={value} onChange={(event) => onChange(event.target.value)} /></label>
}

function Actions({ busy, cancel, label }: { busy: boolean; cancel: () => void; label: string }) {
  return <div className="form-actions"><button type="submit" className="primary-button" disabled={busy}>{busy ? translate('accounting.saving') : label}</button><button type="button" className="secondary-button" onClick={cancel}>{translate('common.cancel')}</button></div>
}
