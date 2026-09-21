import { useEffect, useMemo, useState } from 'react'
import { Download, FileCheck2, History, Mail, Pencil, Plus, Trash2 } from 'lucide-react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'
import type { FormEvent } from 'react'
import { formatPlainDate, translate } from '../i18n/localization'
import type { MessageId } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { InvoiceClient, InvoiceCollectionQuery, InvoiceCollectionResult, InvoiceDraft, InvoiceLine, InvoiceOrigin, TaxRateChoice } from './api'
import { CollectionTable } from '../collections/CollectionTable'
import { CollectionPagination } from '../CollectionPagination'
import { ColumnChooser } from '../collections/ColumnChooser'
import { browserCollectionPreferences, defaultPreferences } from '../collections/preferences'
import type { CollectionPreferences } from '../collections/preferences'
import { FilterMenu } from '../FilterMenu'
import '../collections/collections.css'

import { RecurringInvoices } from './RecurringInvoices'
import { browserRecurringClient } from './recurringApi'

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
type EventForm = {
  event_type: 'payment_recorded' | 'payment_reversed' | 'accounting_synchronized' | 'accounting_rejected' | 'accounting_duplicate' | 'accounting_changed' | 'voided' | 'credited'
  amount: string
  provider: string
  external_id: string
  idempotency_key: string
  related_invoice_id: string
  note: string
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
const emptyEvent = (): EventForm => ({ event_type: 'payment_recorded', amount: '', provider: '', external_id: '', idempotency_key: '', related_invoice_id: '', note: '' })

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
    stock_item: translate('accounting.originStock'),
  }
  const available = origin.origin_type === 'stock_item' && origin.available_quantity && origin.unit
    ? ` · ${translate('accounting.availableStock', { quantity: origin.available_quantity, unit: origin.unit })}`
    : ''
  return `${labels[origin.origin_type]} · ${origin.name}${available} · ${origin.currency} ${origin.unit_amount}`
}

function summaryStatuses(record: InvoiceDraft) {
  const labels = [lifecycleLabel(record.lifecycle_state ?? 'issued'), reconciliationLabel(record.reconciliation_state ?? 'unsynchronized')]
  return [...new Set(labels)].join(' · ')
}

const invoiceColumns = ['name', 'state', 'invoice_date', 'due_date', 'reference', 'total'] as const
const invoiceLabels = {
  name: translate('accounting.invoice'), state: translate('accounting.status'), invoice_date: translate('accounting.invoiceDate'),
  due_date: translate('accounting.dueDate'), reference: translate('accounting.reference'), total: translate('accounting.total'),
}

export function Invoices({ workspace, client, preferenceClient = browserCollectionPreferences }: { workspace: WorkspaceContext; client: InvoiceClient; preferenceClient?: typeof browserCollectionPreferences }) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const [showRecurring, setShowRecurring] = useState(false)
  const [records, setRecords] = useState<InvoiceDraft[]>([])
  const [result, setResult] = useState<InvoiceCollectionResult | null>(null)
  const [selectedRecord, setSelected] = useState<InvoiceDraft | null>(null)
  const [unavailableId, setUnavailableId] = useState<string | null>(null)
  const [preferences, setPreferences] = useState<CollectionPreferences>(() => defaultPreferences(invoiceColumns))
  const [origins, setOrigins] = useState<InvoiceOrigin[]>([])
  const [taxRates, setTaxRates] = useState<TaxRateChoice[]>([])
  const [canManage, setCanManage] = useState(false)
  const [canIssue, setCanIssue] = useState(false)
  const [needsSettings, setNeedsSettings] = useState(false)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [editor, setEditor] = useState<'none' | 'new' | 'draft' | 'line' | 'delivery' | 'event'>('none')
  const [editingLineId, setEditingLineId] = useState<string | null>(null)
  const [draft, setDraft] = useState<DraftForm>(emptyDraft)
  const [line, setLine] = useState<LineForm>(emptyLine)
  const [eventValue, setEventValue] = useState<EventForm>(emptyEvent)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deliveryRecipient, setDeliveryRecipient] = useState('')
  const [confirmation, setConfirmation] = useState<'delete' | 'issue' | null>(null)
  const selectedId = params.get('invoice')
  const selected = selectedRecord?.id === selectedId ? selectedRecord : null
  const requestedPage = Number(params.get('page') ?? 1)
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  const pageSize = [25, 50, 100].includes(Number(params.get('page_size'))) ? Number(params.get('page_size')) : preferences?.page_size ?? 25
  const queryText = JSON.stringify({ q: params.get('q') ?? '', page, page_size: pageSize, ordering: params.get('ordering') ?? '-invoice_date', summary: true, ...(params.get('state') ? { state: params.get('state') } : {}) })
  const query = useMemo(() => JSON.parse(queryText) as InvoiceCollectionQuery, [queryText])

  useEffect(() => {
    const controller = new AbortController()
    preferenceClient.load(workspace, 'invoices', invoiceColumns, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setPreferences(value) })
      .catch(() => { if (!controller.signal.aborted) setPreferences(defaultPreferences(invoiceColumns)) })
    return () => controller.abort()
  }, [workspace, preferenceClient])

  useEffect(() => {
    const controller = new AbortController()
    client.list(workspace, controller.signal, query)
      .then(async (result) => {
        const choices = result.can_manage
          ? await client.choices(workspace, controller.signal)
          : { origins: [], tax_rates: [] }
        setRecords(result.results)
        setResult(result)
        setCanManage(result.can_manage)
        setCanIssue(result.can_issue)
        setOrigins(choices.origins)
        setTaxRates(choices.tax_rates)
        setPhase('ready')
      })
      .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client, workspace, query])

  useEffect(() => {
    if (!selectedId) return
    const controller = new AbortController()
    client.get(workspace, selectedId, controller.signal)
      .then((record) => { if (!controller.signal.aborted) { setSelected(record); setUnavailableId(null) } })
      .catch(() => { if (!controller.signal.aborted) setUnavailableId(selectedId) })
    return () => controller.abort()
  }, [client, workspace, selectedId])

  function browse(values: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    for (const [name, value] of Object.entries(values)) {
      if (value) next.set(name, value)
      else next.delete(name)
    }
    if (!('page' in values)) next.delete('page')
    setParams(next)
  }

  function invoiceHref(id?: string) {
    const next = new URLSearchParams(params)
    next.delete('invoice')
    if (id) next.set('invoice', id)
    return `${location.pathname}${next.size ? `?${next}` : ''}`
  }

  function replace(record: InvoiceDraft) {
    setRecords((current) => current.some((item) => item.id === record.id)
      ? current.map((item) => item.id === record.id ? record : item)
      : [record, ...current])
    setSelected(record)
    if (selectedId !== record.id) void navigate(invoiceHref(record.id))
    setEditor('none')
    setEditingLineId(null)
    setConfirmation(null)
  }

  async function perform(action: () => Promise<InvoiceDraft>, failure: MessageId = 'accounting.changeFailed') {
    setBusy(true)
    setError(null)
    try { replace(await action()) }
    catch { setError(translate(failure)) }
    finally { setBusy(false) }
  }

  async function removeDraft() {
    if (!selected) return
    setBusy(true)
    setError(null)
    try {
      await client.remove(workspace, selected.id)
      setRecords((current) => current.filter((record) => record.id !== selected.id))
      setSelected(null)
      void navigate(invoiceHref())
      setConfirmation(null)
    } catch {
      setError(translate('accounting.deleteFailed'))
    } finally { setBusy(false) }
  }

  function beginLine(record?: InvoiceLine) {
    setEditingLineId(record?.id ?? null)
    setLine(record ? lineForm(record) : emptyLine())
    setEditor('line')
  }

  async function issueSelected() {
    if (!selected) return
    setBusy(true)
    setError(null)
    setNeedsSettings(false)
    try { replace(await client.issue(workspace, selected.id)) }
    catch (caught) {
      const message = caught instanceof Error ? caught.message : translate('accounting.changeFailed')
      if (message.toLowerCase().includes('configure')) {
        setNeedsSettings(true)
        setError(translate('accounting.settingsRequired'))
      } else {
        setError(translate('accounting.issueFailed'))
      }
    } finally { setBusy(false) }
  }

  async function deliverSelected(event: FormEvent) {
    event.preventDefault()
    if (!selected) return
    await perform(() => client.deliver(workspace, selected.id, deliveryRecipient), 'accounting.deliveryFailed')
  }
  const collectionRows = records.map((record) => ({
    ...record,
    name: record.number || formatPlainDate(record.invoice_date),
  }))

  return <>
    <header className="page-header">
      <div><h1>{translate('accounting.heading')}</h1></div>
      <div className="form-actions">
        {canManage && !selectedId && <button type="button" className="secondary-button" aria-expanded={showRecurring} onClick={() => setShowRecurring(!showRecurring)}>{translate(showRecurring ? 'recurring.close' : 'recurring.title')}</button>}
        {canManage && <button type="button" className="primary-button" aria-label={translate('accounting.newDraft')} onClick={() => { setDraft(emptyDraft()); setEditor('new') }}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('accounting.newDraft')}</span></button>}
      </div>
    </header>
    {showRecurring && <RecurringInvoices key={workspace.id} workspace={workspace} client={browserRecurringClient} openInvoice={async (id) => {
      await client.get(workspace, id)
      setShowRecurring(false)
      void navigate(invoiceHref(id))
    }} />}
    {error && <div className="form-message error" role="alert">{error}{needsSettings && <> <Link to="/invoices">{translate('accounting.openSettings')}</Link></>}</div>}
    {phase === 'loading' && <section className="content-section" role="status">{translate('accounting.loading')}</section>}
    {phase === 'error' && <section className="content-section workspace-error" role="alert"><h2>{translate('accounting.unavailable')}</h2><p>{translate('accounting.loadFailed')}</p></section>}
    {phase === 'ready' && !selectedId && <>
      <div className="collection-toolbar">
        <form key={query.q} className="collection-search" onSubmit={(event) => { event.preventDefault(); const value = new FormData(event.currentTarget).get('q'); browse({ q: typeof value === 'string' ? value : '' }) }}><input type="search" name="q" defaultValue={query.q} aria-label={translate('accounting.search')} /><button type="submit" className="secondary-button">{translate('accounting.searchAction')}</button></form>
        <FilterMenu groups={[{ kind: 'choices', label: translate('accounting.status'), value: query.state ?? '', choices: [{ value: '', label: translate('collections.all') }, { value: 'draft', label: translate('accounting.draft') }, { value: 'issued', label: translate('accounting.issued') }], onChange: (state) => browse({ state: state || null }) }]} activeCount={Number(Boolean(query.state))} onClear={() => browse({ state: null })} />
        <ColumnChooser preferences={preferences} labels={invoiceLabels} onSave={async (columns) => setPreferences(await preferenceClient.save(workspace, 'invoices', { columns, page_size: pageSize as 25 | 50 | 100 }))} onReset={async () => setPreferences(await preferenceClient.reset(workspace, 'invoices'))} />
        <label className="collection-page-size">{translate('collections.pageSize')}<select value={pageSize} onChange={(event) => { const size = Number(event.target.value) as 25 | 50 | 100; browse({ page_size: String(size) }); void preferenceClient.save(workspace, 'invoices', { columns: preferences.columns, page_size: size }).then(setPreferences).catch(() => setError(translate('collections.preferenceFailed'))) }}>{[25, 50, 100].map((size) => <option key={size}>{size}</option>)}</select></label>
      </div>
      <div className="collection-active-filters">{query.state && <button type="button" className="row-action" onClick={() => browse({ state: null })}>{translate('accounting.status')}: {query.state} ×</button>}</div>
      <label className="collection-mobile-order">{translate('accounting.ordering')}<select value={query.ordering} onChange={(event) => browse({ ordering: event.target.value })}>{invoiceColumns.flatMap((column) => [<option key={column} value={column}>{invoiceLabels[column]} ↑</option>, <option key={`-${column}`} value={`-${column}`}>{invoiceLabels[column]} ↓</option>])}</select></label>
      <p>{translate('accounting.count', { count: result?.count ?? 0 })}</p>
      {records.length === 0 ? <p className="empty-state">{translate('accounting.empty')}</p> : <CollectionTable label={translate('accounting.heading')} rows={collectionRows} selectable={false} selected={new Set()} onSelection={() => {}} ordering={query.ordering} onOrder={(ordering) => browse({ ordering })} columns={preferences.columns.map((column) => ({ id: column, label: invoiceLabels[column as keyof typeof invoiceLabels], render: (record: InvoiceDraft & { name: string }) => {
        if (column === 'name') return <button type="button" className="collection-name" onClick={() => { setConfirmation(null); void navigate(invoiceHref(record.id)) }}>{record.number || formatPlainDate(record.invoice_date)}</button>
        if (column === 'state') return record.state === 'draft' ? translate('accounting.draft') : summaryStatuses(record)
        if (column === 'invoice_date' || column === 'due_date') return formatPlainDate(record[column])
        if (column === 'total') return `${record.currency} ${record.total}`
        return record.reference || translate('collections.missing')
      } }))} />}
      {result && <CollectionPagination label={translate('accounting.heading')} page={page} pageSize={pageSize} count={result.count} hasMore={result.has_more} onPageChange={(next) => browse({ page: String(next) })} />}
    </>}
    {phase === 'ready' && selectedId && <>
      <Link to={invoiceHref()}>{translate('accounting.return')}</Link>
      <section className="content-section inventory-detail">
        {selected ? <>
          <div className="section-heading"><div><h2>{selected.number || `${translate('accounting.draft')} · ${formatPlainDate(selected.invoice_date)}`}</h2><p>{selected.reference || workspace.name}</p></div><span className="lifecycle-state">{translate(selected.state === 'draft' ? 'accounting.draft' : 'accounting.issued')}</span></div>
          <dl className="inventory-provenance">
            <div><dt>{translate('accounting.invoiceDate')}</dt><dd>{formatPlainDate(selected.invoice_date)}</dd></div>
            <div><dt>{translate('accounting.dueDate')}</dt><dd>{formatPlainDate(selected.due_date)}</dd></div>
            <div><dt>{translate('accounting.currency')}</dt><dd>{selected.currency}</dd></div>
            <div><dt>{translate('accounting.reference')}</dt><dd>{selected.reference || '—'}</dd></div>
          </dl>
          {selected.notes && <p>{selected.notes}</p>}
          {selected.state === 'draft' && <div className="form-actions">{canManage && <><button type="button" className="secondary-button" onClick={() => { setConfirmation(null); setDraft(draftForm(selected)); setEditor('draft') }}><Pencil size={15} />{translate('accounting.editDraft')}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => setConfirmation('delete')}><Trash2 size={15} />{translate('accounting.deleteDraft')}</button></>}{canIssue && <button type="button" className="primary-button" disabled={busy || selected.lines.length === 0} onClick={() => setConfirmation('issue')}><FileCheck2 size={15} />{translate('accounting.issue')}</button>}</div>}
          {selected.state === 'draft' && confirmation && <div className="archive-confirmation" role="alertdialog" aria-labelledby="invoice-confirmation-heading" aria-describedby="invoice-confirmation-help"><div><strong id="invoice-confirmation-heading">{translate(confirmation === 'issue' ? 'accounting.issueConfirmHeading' : 'accounting.deleteDraftConfirmHeading', { date: formatPlainDate(selected.invoice_date) })}</strong><p id="invoice-confirmation-help">{translate(confirmation === 'issue' ? 'accounting.issueConfirmHelp' : 'accounting.deleteDraftConfirmHelp')}</p></div><div className="form-actions"><button type="button" className={confirmation === 'delete' ? 'danger-button' : 'primary-button'} disabled={busy} onClick={() => { void (confirmation === 'issue' ? issueSelected() : removeDraft()) }}>{busy ? translate(confirmation === 'issue' ? 'accounting.issuing' : 'accounting.deleting') : translate(confirmation === 'issue' ? 'accounting.issue' : 'accounting.deleteDraft')}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => setConfirmation(null)}>{translate('common.cancel')}</button></div></div>}
          {selected.state === 'issued' && selected.issued_at && <p className="workspace-area-note">{translate(selected.key_fingerprint ? 'accounting.issuedProofVerified' : 'accounting.issuedProof', { date: formatPlainDate(selected.issued_at.slice(0, 10)), fingerprint: selected.key_fingerprint?.slice(0, 12) ?? '' })}</p>}
          {selected.state === 'issued' && <div className="form-actions">
            <a className="secondary-button" href={client.pdfUrl(workspace, selected.id)}><Download size={15} aria-hidden="true" />{translate('accounting.downloadPdf')}</a>
            <a className="secondary-button" href={client.csvUrl(workspace, selected.id)}><Download size={15} aria-hidden="true" />{translate('accounting.downloadCsv')}</a>
            <a className="secondary-button" href={client.accountingExportUrl(workspace, selected.id)}><Download size={15} aria-hidden="true" />{translate('accounting.accountingExport')}</a>
            {canIssue && <button type="button" className="primary-button" disabled={busy} onClick={() => { setDeliveryRecipient(''); setEditor('delivery') }}><Mail size={15} aria-hidden="true" />{translate('accounting.deliver')}</button>}
            {canIssue && <button type="button" className="secondary-button" disabled={busy} onClick={() => { setEventValue(emptyEvent()); setEditor('event') }}><History size={15} aria-hidden="true" />{translate('accounting.recordUpdate')}</button>}
          </div>}
          {selected.state === 'issued' && selected.delivered_at && <p className="workspace-area-note">{translate((selected.delivery_count ?? 1) === 1 ? 'accounting.deliveredProof' : 'accounting.deliveredProofPlural', { date: formatPlainDate(selected.delivered_at.slice(0, 10)), count: selected.delivery_count ?? 1 })}</p>}
          {selected.state === 'issued' && <dl className="inventory-provenance">
            <div><dt>{translate('accounting.lifecycle')}</dt><dd>{lifecycleLabel(selected.lifecycle_state ?? 'issued')}</dd></div>
            <div><dt>{translate('accounting.reconciliation')}</dt><dd>{reconciliationLabel(selected.reconciliation_state ?? 'unsynchronized')}</dd></div>
            <div><dt>{translate('accounting.paid')}</dt><dd>{selected.currency} {selected.paid_amount ?? '0.00'}</dd></div>
            <div><dt>{translate('accounting.balance')}</dt><dd>{selected.currency} {selected.balance_amount ?? selected.total}</dd></div>
          </dl>}
          {selected.state === 'issued' && (selected.lifecycle_events?.length ?? 0) > 0 && <section aria-labelledby="invoice-history-heading"><div className="section-heading"><h3 id="invoice-history-heading">{translate('accounting.history')}</h3></div><ol className="invoice-event-list">{[...(selected.lifecycle_events ?? [])].reverse().map((item) => <li key={item.id}><div><strong>{eventLabel(item.event_type)}</strong><span>{formatPlainDate(item.occurred_at.slice(0, 10))}{item.actor ? ` · ${item.actor}` : ''}</span></div><span>{item.amount ? `${item.currency} ${item.amount}` : item.provider || item.note}</span></li>)}</ol></section>}
          <div className="section-heading"><h3>{translate('accounting.lines')}</h3>{canManage && selected.state === 'draft' && <button type="button" className="secondary-button" onClick={() => beginLine()}><Plus size={15} />{translate('accounting.addLine')}</button>}</div>
          {selected.lines.length === 0 ? <p className="empty-state">{translate('accounting.noLines')}</p> : <ul className="inventory-list">{selected.lines.map((item) => <li key={item.id}><div><strong>{item.description}</strong><span>{item.quantity} × {item.currency} {item.unit_amount}{item.tax_rate_name ? ` · ${item.tax_rate_name}` : ''}</span></div><div><strong>{item.currency} {item.total}</strong>{canManage && selected.state === 'draft' && <div className="form-actions"><button type="button" className="text-button" aria-label={translate('accounting.editLine', { description: item.description })} onClick={() => beginLine(item)}>{translate('common.edit')}</button><button type="button" className="text-button" aria-label={translate('accounting.deleteLine', { description: item.description })} onClick={() => { void perform(() => client.removeLine(workspace, selected.id, item.id)) }}>{translate('common.remove')}</button></div>}</div></li>)}</ul>}
          <dl className="inventory-provenance">
            <div><dt>{translate('accounting.subtotal')}</dt><dd>{selected.currency} {selected.subtotal}</dd></div>
            <div><dt>{translate('accounting.tax')}</dt><dd>{selected.currency} {selected.tax_total}</dd></div>
            <div><dt>{translate('accounting.total')}</dt><dd><strong>{selected.currency} {selected.total}</strong></dd></div>
          </dl>
        </> : unavailableId === selectedId ? <p role="alert">{translate('accounting.loadFailed')}</p> : <p role="status">{translate('accounting.loading')}</p>}
      </section>
    </>}
    {(editor === 'new' || editor === 'draft') && <DraftEditor value={draft} setValue={setDraft} busy={busy} title={editor === 'new' ? translate('accounting.newDraftTitle') : translate('accounting.editDraftTitle')} cancel={() => setEditor('none')} submit={() => { void perform(() => editor === 'new' ? client.create(workspace, draft) : client.update(workspace, selected!.id, draft)) }} />}
    {editor === 'line' && selected && <LineEditor value={line} setValue={setLine} origins={origins.filter((origin) => origin.currency === selected.currency)} taxRates={taxRates} adjustsExistingStock={Boolean(editingLineId && selected.lines.find((item) => item.id === editingLineId)?.origin_type === 'stock_item')} busy={busy} cancel={() => setEditor('none')} submit={() => { const [origin_type, origin_id] = line.originKey.split(':'); const selectedOrigin = origins.find((origin) => `${origin.origin_type}:${origin.id}` === line.originKey); const selectedTax = taxRates.find((rate) => rate.id === line.tax_rate_id); const values = editingLineId ? { description: line.description, quantity: line.quantity, unit_amount: line.unit_amount, tax_rate_name: selectedTax?.name ?? line.tax_rate_name, tax_rate_value: selectedTax?.rate ?? line.tax_rate_value, tax_inclusive: selectedTax?.inclusive ?? line.tax_inclusive } : line.originKey ? { origin_type, origin_id, ...(selectedOrigin?.origin_type === 'stock_item' ? { quantity: line.quantity } : {}), tax_rate_id: line.tax_rate_id || null } : { description: line.description, quantity: line.quantity, unit_amount: line.unit_amount, tax_rate_id: line.tax_rate_id || null }; void perform(() => editingLineId ? client.updateLine(workspace, selected.id, editingLineId, values) : client.addLine(workspace, selected.id, values)) }} />}
    {editor === 'delivery' && selected && <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="invoice-delivery-title"><form className="record-form" onSubmit={(event) => { void deliverSelected(event) }}><div className="section-heading"><h2 id="invoice-delivery-title">{translate('accounting.deliverTitle')}</h2></div><label><span>{translate('accounting.deliveryRecipient')}</span><input autoFocus type="email" required maxLength={254} autoComplete="email" value={deliveryRecipient} onChange={(event) => setDeliveryRecipient(event.target.value)} /></label><p>{translate('accounting.deliveryDescription')}</p><div className="form-actions"><button type="button" className="secondary-button" onClick={() => setEditor('none')}>{translate('common.cancel')}</button><button type="submit" className="primary-button" disabled={busy}>{busy ? translate('accounting.sending') : translate('accounting.send')}</button></div></form></section>}
    {editor === 'event' && selected && <InvoiceEventEditor value={eventValue} setValue={setEventValue} invoices={records.filter((item) => item.state === 'issued' && item.id !== selected.id)} currency={selected.currency} busy={busy} cancel={() => setEditor('none')} submit={() => { const payment = eventValue.event_type === 'payment_recorded' || eventValue.event_type === 'payment_reversed'; const provider = eventValue.event_type.startsWith('accounting_'); void perform(() => client.recordEvent(workspace, selected.id, { event_type: eventValue.event_type, occurred_at: new Date().toISOString(), amount: payment ? eventValue.amount : null, currency: payment ? selected.currency : '', provider: provider ? eventValue.provider : '', external_id: provider ? eventValue.external_id : '', idempotency_key: provider ? eventValue.idempotency_key : `tekdocs:invoice:${selected.id}:${eventValue.event_type}:${crypto.randomUUID()}`, related_invoice_id: eventValue.related_invoice_id || null, note: eventValue.note }), 'accounting.updateFailed') }} />}
  </>
}

function InvoiceEventEditor({ value, setValue, invoices, currency, busy, cancel, submit }: { value: EventForm; setValue: (value: EventForm) => void; invoices: InvoiceDraft[]; currency: string; busy: boolean; cancel: () => void; submit: () => void }) {
  const payment = value.event_type === 'payment_recorded' || value.event_type === 'payment_reversed'
  const provider = value.event_type.startsWith('accounting_')
  const linked = value.event_type === 'voided' || value.event_type === 'credited'
  return <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="invoice-event-title"><form className="record-form" onSubmit={(formEvent) => { formEvent.preventDefault(); submit() }}><div className="section-heading"><h2 id="invoice-event-title">{translate('accounting.recordUpdate')}</h2></div><label><span>{translate('accounting.updateType')}</span><select autoFocus value={value.event_type} onChange={(event) => setValue({ ...value, event_type: event.target.value as EventForm['event_type'] })}>{EVENT_OPTIONS.map(([key, label]) => <option key={key} value={key}>{translate(label)}</option>)}</select></label>
    {payment && <label><span>{translate('accounting.paymentAmount')} ({currency})</span><input required type="number" min="0.0001" step="0.0001" value={value.amount} onChange={(event) => setValue({ ...value, amount: event.target.value })} /></label>}
    {provider && <><label><span>{translate('accounting.provider')}</span><input required maxLength={80} value={value.provider} onChange={(event) => setValue({ ...value, provider: event.target.value })} /></label><label><span>{translate('accounting.externalId')}</span><input required maxLength={160} value={value.external_id} onChange={(event) => setValue({ ...value, external_id: event.target.value })} /></label><label><span>{translate('accounting.idempotencyKey')}</span><input required maxLength={160} aria-describedby="invoice-update-id-help" value={value.idempotency_key} onChange={(event) => setValue({ ...value, idempotency_key: event.target.value })} /></label><p id="invoice-update-id-help" className="field-help wide-field">{translate('accounting.idempotencyHelp')}</p></>}
    {linked && invoices.length > 0 && <label><span>{translate('accounting.relatedInvoice')}</span><select value={value.related_invoice_id} onChange={(event) => setValue({ ...value, related_invoice_id: event.target.value })}><option value="">{translate('accounting.noRelatedInvoice')}</option>{invoices.map((invoice) => <option key={invoice.id} value={invoice.id}>{invoice.number}</option>)}</select></label>}
    <label><span>{translate('accounting.updateNote')}</span><textarea required={linked} maxLength={500} rows={3} value={value.note} onChange={(event) => setValue({ ...value, note: event.target.value })} /></label><div className="form-actions"><button type="submit" className="primary-button" disabled={busy}>{busy ? translate('accounting.saving') : translate('accounting.recordUpdate')}</button><button type="button" className="secondary-button" onClick={cancel}>{translate('common.cancel')}</button></div></form></section>
}

const EVENT_OPTIONS: ReadonlyArray<readonly [EventForm['event_type'], MessageId]> = [
  ['payment_recorded', 'accounting.paymentRecorded'], ['payment_reversed', 'accounting.paymentReversed'],
  ['accounting_synchronized', 'accounting.synchronized'], ['accounting_rejected', 'accounting.rejected'],
  ['accounting_duplicate', 'accounting.duplicate'], ['accounting_changed', 'accounting.externallyChanged'],
  ['voided', 'accounting.voided'], ['credited', 'accounting.credited'],
]

function eventLabel(value: string) { return translate(`accounting.event.${value}` as MessageId) }
function lifecycleLabel(value: string) { return translate(`accounting.lifecycle.${value}` as MessageId) }
function reconciliationLabel(value: string) { return translate(`accounting.reconciliation.${value}` as MessageId) }

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

function LineEditor({ value, setValue, origins, taxRates, adjustsExistingStock, busy, cancel, submit }: { value: LineForm; setValue: (value: LineForm) => void; origins: InvoiceOrigin[]; taxRates: TaxRateChoice[]; adjustsExistingStock: boolean; busy: boolean; cancel: () => void; submit: () => void }) {
  function save(event: FormEvent) { event.preventDefault(); submit() }
  const selectedOrigin = origins.find((item) => `${item.origin_type}:${item.id}` === value.originKey)
  const stockOrigin = selectedOrigin?.origin_type === 'stock_item' ? selectedOrigin : null
  return <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="invoice-line-editor-title"><form className="record-form" onSubmit={save}><div className="section-heading"><h2 id="invoice-line-editor-title">{translate('accounting.lineTitle')}</h2></div><div className="form-grid">
    <label className="wide-field"><span>{translate('accounting.origin')}</span><select value={value.originKey} onChange={(event) => { const origin = origins.find((item) => `${item.origin_type}:${item.id}` === event.target.value); setValue(origin ? { ...value, originKey: event.target.value, description: origin.name, quantity: origin.quantity, unit_amount: origin.unit_amount } : { ...value, originKey: '' }) }}><option value="">{translate('accounting.manualLine')}</option>{origins.map((origin) => <option key={`${origin.origin_type}:${origin.id}`} value={`${origin.origin_type}:${origin.id}`}>{originLabel(origin)}</option>)}</select></label>
    <Field label={translate('accounting.description')} value={value.description} disabled={Boolean(value.originKey)} onChange={(description) => setValue({ ...value, description })} />
    <Field label={translate('accounting.quantity')} type="number" step="0.001" min="0.001" max={stockOrigin?.available_quantity} value={value.quantity} disabled={Boolean(value.originKey) && !stockOrigin} onChange={(quantity) => setValue({ ...value, quantity })} />
    <Field label={translate('accounting.unitAmount')} type="number" step="0.0001" value={value.unit_amount} disabled={Boolean(value.originKey)} onChange={(unit_amount) => setValue({ ...value, unit_amount })} />
    {stockOrigin && <p className="wide-field workspace-area-note">{translate('accounting.stockConsumptionHelp', { quantity: stockOrigin.available_quantity ?? '', unit: stockOrigin.unit ?? '' })}</p>}
    {adjustsExistingStock && <p className="wide-field workspace-area-note">{translate('accounting.stockEditHelp')}</p>}
    <label><span>{translate('accounting.taxRate')}</span><select value={value.tax_rate_id} onChange={(event) => setValue(event.target.value ? { ...value, tax_rate_id: event.target.value } : { ...value, tax_rate_id: '', tax_rate_name: '', tax_rate_value: '0', tax_inclusive: false })}><option value="">{translate('accounting.noTax')}</option>{value.tax_rate_id === '__snapshot__' && <option value="__snapshot__">{value.tax_rate_name} · {value.tax_rate_value}</option>}{taxRates.map((rate) => <option key={rate.id} value={rate.id}>{rate.name} · {rate.rate}{rate.inclusive ? ` · ${translate('accounting.includedInPrice')}` : ''}</option>)}</select></label>
  </div><Actions busy={busy || (!value.originKey && (!value.description.trim() || !value.unit_amount))} cancel={cancel} label={translate('accounting.saveLine')} /></form></section>
}

function Field({ label, value, onChange, type = 'text', step, min, max, disabled = false, required = true, autoFocus = false }: { label: string; value: string; onChange: (value: string) => void; type?: string; step?: string; min?: string; max?: string; disabled?: boolean; required?: boolean; autoFocus?: boolean }) {
  return <label><span>{label}</span><input autoFocus={autoFocus} required={required} disabled={disabled} type={type} step={step} min={min ?? (type === 'number' ? 0 : undefined)} max={max} value={value} onChange={(event) => onChange(event.target.value)} /></label>
}

function Actions({ busy, cancel, label }: { busy: boolean; cancel: () => void; label: string }) {
  return <div className="form-actions"><button type="submit" className="primary-button" disabled={busy}>{busy ? translate('accounting.saving') : label}</button><button type="button" className="secondary-button" onClick={cancel}>{translate('common.cancel')}</button></div>
}
