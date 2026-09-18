import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Archive, ArrowDown, ArrowUp, ExternalLink, Pencil, Plus, Search } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { QuickDrawer } from '../collections/QuickDrawer'
import '../collections/collections.css'
import { formatPlainDate, translate } from '../i18n/localization'
import type { StockChoice, StockClient, StockItem, StockOrdering, StockQuery, StockResult } from './api'

type ItemForm = {
  name: string; description: string; vendor_id: string; vendor_part_number: string; unit: string
  initial_quantity: string; reorder_level: string; currency: string; cost_per_unit: string
  client_price_per_unit: string; purchase_quantity: string; purchase_price: string; order_total: string
  order_number: string; order_url: string; ordered_on: string; tracking_number: string; tracking_url: string
}
type MoveForm = { action: 'received' | 'used' | 'returned' | 'correction_add' | 'correction_remove'; quantity: string; client_id: string; note: string; occurred_on: string }

const initialQuery: StockQuery = { q: '', ordering: 'name', page: 1, page_size: 25 }
const emptyItem = (): ItemForm => ({ name: '', description: '', vendor_id: '', vendor_part_number: '', unit: 'each', initial_quantity: '0', reorder_level: '', currency: 'USD', cost_per_unit: '', client_price_per_unit: '', purchase_quantity: '', purchase_price: '', order_total: '', order_number: '', order_url: '', ordered_on: '', tracking_number: '', tracking_url: '' })
const emptyMove = (): MoveForm => ({ action: 'received', quantity: '', client_id: '', note: '', occurred_on: new Date().toISOString().slice(0, 10) })

function itemForm(item: StockItem): ItemForm {
  return { name: item.name, description: item.description, vendor_id: item.vendor_id ?? '', vendor_part_number: item.vendor_part_number, unit: item.unit, initial_quantity: '0', reorder_level: item.reorder_level ?? '', currency: item.currency, cost_per_unit: item.cost_per_unit, client_price_per_unit: item.client_price_per_unit, purchase_quantity: item.purchase_quantity ?? '', purchase_price: item.purchase_price ?? '', order_total: item.order_total ?? '', order_number: item.order_number, order_url: item.order_url, ordered_on: item.ordered_on ?? '', tracking_number: item.tracking_number, tracking_url: item.tracking_url }
}

function payload(value: ItemForm, creating: boolean) {
  return {
    name: value.name.trim(), description: value.description.trim(), vendor_id: value.vendor_id || null,
    vendor_part_number: value.vendor_part_number.trim(), unit: value.unit.trim(), currency: value.currency.toUpperCase(),
    cost_per_unit: value.cost_per_unit, client_price_per_unit: value.client_price_per_unit,
    reorder_level: value.reorder_level || null, purchase_quantity: value.purchase_quantity || null,
    purchase_price: value.purchase_price || null, order_total: value.order_total || null,
    order_number: value.order_number.trim(), order_url: value.order_url.trim(), ordered_on: value.ordered_on || null,
    tracking_number: value.tracking_number.trim(), tracking_url: value.tracking_url.trim(),
    ...(creating ? { initial_quantity: value.initial_quantity || '0' } : {}),
  }
}

function queryFrom(parameters: URLSearchParams): StockQuery {
  const ordering = parameters.get('stock_order') as StockOrdering | null
  const validOrdering: StockOrdering[] = ['name', '-name', 'quantity_on_hand', '-quantity_on_hand', 'updated_at', '-updated_at']
  const page = Number(parameters.get('stock_page'))
  return {
    ...initialQuery,
    q: parameters.get('q') ?? '',
    ordering: ordering && validOrdering.includes(ordering) ? ordering : 'name',
    page: Number.isInteger(page) && page > 0 ? page : 1,
  }
}

export function Stock({ client }: { client: StockClient }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const query = useMemo(() => queryFrom(searchParams), [searchParams])
  const [result, setResult] = useState<StockResult | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [revision, setRevision] = useState(0)
  const drawerId = searchParams.get('stock')
  const [selected, setSelected] = useState<StockItem | null>(null)
  const [drawerErrorId, setDrawerErrorId] = useState<string | null>(null)
  const [mode, setMode] = useState<'view' | 'edit' | 'move'>('view')
  const [dirty, setDirty] = useState(false)
  const [confirmingClose, setConfirmingClose] = useState(false)
  const [confirmingArchive, setConfirmingArchive] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setPhase('loading')
      client.list(query, controller.signal)
        .then((value) => { setResult(value); setPhase('ready') })
        .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    }, query.q ? 250 : 0)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, query, revision])

  const listedRecord = drawerId ? result?.results.find((item) => item.id === drawerId) ?? null : null
  const drawerRecord = drawerId && drawerId !== 'new' ? (selected?.id === drawerId ? selected : listedRecord) : null
  const drawerPhase = drawerId === 'new'
    ? !result ? 'loading' : result.can_manage ? 'ready' : 'denied'
    : drawerRecord ? 'ready' : drawerErrorId === drawerId ? 'error' : 'loading'
  const drawerMode = drawerId === 'new' ? 'edit' : mode
  const itemEditorValue = useMemo(() => drawerRecord ? itemForm(drawerRecord) : emptyItem(), [drawerRecord])
  const [movementEditorValue] = useState(emptyMove)

  useEffect(() => {
    if (!drawerId || drawerId === 'new' || drawerRecord) return
    const controller = new AbortController()
    client.retrieve(drawerId, controller.signal)
      .then((item) => { setSelected(item); setDrawerErrorId(null) })
      .catch(() => { if (!controller.signal.aborted) setDrawerErrorId(drawerId) })
    return () => controller.abort()
  }, [client, drawerId, drawerRecord])

  const updateUrl = useCallback((changes: { q?: string; ordering?: StockOrdering; page?: number; stock?: string | null }, replace = false) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (changes.q !== undefined) {
        if (changes.q) next.set('q', changes.q)
        else next.delete('q')
      }
      if (changes.ordering !== undefined) {
        if (changes.ordering === 'name') next.delete('stock_order')
        else next.set('stock_order', changes.ordering)
      }
      if (changes.page !== undefined) {
        if (changes.page === 1) next.delete('stock_page')
        else next.set('stock_page', String(changes.page))
      }
      if (changes.stock !== undefined) {
        if (changes.stock) next.set('stock', changes.stock)
        else next.delete('stock')
      }
      return next
    }, { replace })
  }, [setSearchParams])

  const changeQuery = (changes: Partial<StockQuery>) => {
    const next = { ...query, ...changes, page: changes.page ?? 1 }
    updateUrl({ q: next.q, ordering: next.ordering, page: next.page }, true)
  }
  const openRecord = (item: StockItem, nextMode: 'view' | 'edit' = 'view') => {
    setSelected(item); setMode(nextMode); setError(null); setMessage(null); setConfirmingArchive(false); updateUrl({ stock: item.id })
  }
  const finishClose = () => {
    setDirty(false); setConfirmingClose(false); setConfirmingArchive(false); setMode('view'); setError(null); updateUrl({ stock: null })
  }
  const closeDrawer = () => {
    if (busy) return
    if (dirty) { setConfirmingClose(true); return }
    finishClose()
  }

  async function saveItem(value: ItemForm) {
    setBusy(true); setError(null); setMessage(null)
    try {
      const creating = drawerId === 'new'
      const record = creating ? await client.create(payload(value, true)) : await client.update(drawerId!, payload(value, false))
      setSelected(record); setDirty(false); setMode('view'); updateUrl({ stock: record.id }, creating); setMessage(creating ? `${record.name} was added.` : `${record.name} was updated.`); setRevision((current) => current + 1)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The stock item could not be saved.') }
    finally { setBusy(false) }
  }

  async function saveMovement(value: MoveForm) {
    if (!selected) return
    const negative = value.action === 'used' || value.action === 'correction_remove'
    const movement_type = value.action.startsWith('correction') ? 'correction' : value.action
    setBusy(true); setError(null); setMessage(null)
    try {
      const record = await client.move(selected.id, { movement_type, quantity_change: `${negative ? '-' : ''}${value.quantity}`, client_id: value.action === 'used' ? value.client_id || null : null, note: value.note, occurred_at: `${value.occurred_on}T12:00:00Z` })
      setSelected(record); setDirty(false); setMode('view'); setMessage('Stock quantity was updated.'); setRevision((current) => current + 1)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The stock quantity could not be changed.') }
    finally { setBusy(false) }
  }

  async function archiveSelected() {
    if (!selected) return
    setBusy(true); setError(null)
    try { await client.archive(selected.id); finishClose(); setRevision((current) => current + 1) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'The stock item could not be archived.'); setConfirmingArchive(false) }
    finally { setBusy(false) }
  }

  const sort = (field: 'name' | 'quantity_on_hand') => {
    const next = query.ordering === field ? `-${field}` as StockOrdering : field
    changeQuery({ ordering: next })
  }
  const indicator = (field: string) => query.ordering === field ? <ArrowUp size={13} aria-hidden="true" /> : query.ordering === `-${field}` ? <ArrowDown size={13} aria-hidden="true" /> : null
  const canManage = result?.can_manage ?? false

  return <>
    <header className="page-header"><div><h1>Stock</h1><p>Supplies kept by the MSP for use at any client.</p></div>{canManage && <button className="primary-button" type="button" onClick={() => { setSelected(null); setMode('edit'); setError(null); setMessage(null); updateUrl({ stock: 'new' }) }}><Plus size={16} aria-hidden="true" />{translate('stock.newItem')}</button>}</header>
    {error && !drawerId && <div className="form-message error" role="alert">{error}</div>}{message && !drawerId && <div className="form-success" role="status">{message}</div>}
    {drawerId && <QuickDrawer title={drawerId === 'new' ? 'New stock item' : drawerRecord?.name ?? 'Stock item'} onClose={closeDrawer} returnFocusId={drawerId === 'new' ? undefined : `stock-row-${drawerId}`} returnHref="/stock" returnLabel="Back to stock">
      {error && <div className="form-message error" role="alert">{error}</div>}{message && <div className="form-success" role="status">{message}</div>}
      {drawerPhase === 'loading' && <p role="status">Loading stock item…</p>}{drawerPhase === 'error' && <div className="workspace-error" role="alert"><h3>Stock item unavailable</h3><p>It may have been archived or you may no longer have access.</p></div>}{drawerPhase === 'denied' && <div className="workspace-error" role="alert"><h3>Item creation unavailable</h3><p>You do not have permission to manage stock.</p></div>}
      {drawerPhase === 'ready' && drawerMode === 'edit' && <ItemEditor key={`${drawerId}-${drawerRecord?.updated_at ?? 'new'}`} value={itemEditorValue} vendors={result?.vendors ?? []} creating={drawerId === 'new'} busy={busy} onDirtyChange={setDirty} cancel={drawerId === 'new' ? closeDrawer : () => { setDirty(false); setError(null); setMode('view') }} submit={saveItem} />}
      {drawerPhase === 'ready' && drawerMode === 'move' && drawerRecord && <MovementEditor key={drawerRecord.updated_at} item={drawerRecord} value={movementEditorValue} clients={result?.clients ?? []} busy={busy} onDirtyChange={setDirty} cancel={() => { setDirty(false); setError(null); setMode('view') }} submit={saveMovement} />}
      {drawerPhase === 'ready' && drawerMode === 'view' && drawerRecord && <StockRecord item={drawerRecord} canManage={canManage} onEdit={() => { setSelected(drawerRecord); setMode('edit') }} onMove={() => { setSelected(drawerRecord); setMode('move') }} onArchive={() => { setSelected(drawerRecord); setConfirmingArchive(true) }} />}
      {confirmingArchive && drawerRecord && <div className="archive-confirmation" role="alertdialog" aria-labelledby="stock-archive-heading"><div><strong id="stock-archive-heading">Archive {drawerRecord.name}?</strong><p>Its stock history will be retained.</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={busy} onClick={() => { void archiveSelected() }}>{translate('stock.archiveItem')}</button><button className="secondary-button" type="button" disabled={busy} onClick={() => setConfirmingArchive(false)}>{translate('common.cancel')}</button></div></div>}
      {confirmingClose && <div className="archive-confirmation" role="alertdialog" aria-labelledby="stock-unsaved-heading"><div><strong id="stock-unsaved-heading">Unsaved changes</strong><p>Your changes have not been saved.</p></div><div className="form-actions"><button autoFocus className="primary-button" type="button" onClick={() => setConfirmingClose(false)}>{translate('navigation.unsaved.keep')}</button><button className="secondary-button" type="button" onClick={finishClose}>{translate('navigation.unsaved.discard')}</button></div></div>}
    </QuickDrawer>}
    <section className="content-section stock-list" aria-labelledby="stock-list-heading">
      <div className="section-heading"><div><h2 id="stock-list-heading">Stock items</h2><span>{result ? `${result.count} ${result.count === 1 ? 'item' : 'items'}` : 'Loading'}</span></div></div>
      <label className="site-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search stock</span><input type="search" aria-label="Search stock" value={query.q} onChange={(event) => changeQuery({ q: event.target.value })} placeholder="Item, vendor, part number, or description" /></label>
      {phase === 'loading' && <p role="status">Loading stock…</p>}{phase === 'error' && <div className="workspace-error" role="alert"><h2>Stock unavailable</h2><p>Stock could not be loaded.</p></div>}
      {phase === 'ready' && result?.results.length === 0 && <p className="empty-state">{query.q ? 'No stock matches this search.' : 'No stock items have been created.'}</p>}
      {phase === 'ready' && result && result.results.length > 0 && <div className="people-table-wrap" role="group" aria-label={translate('stock.itemsTable')} tabIndex={0}><table className="people-table stock-table"><thead><tr><th scope="col" aria-sort={query.ordering === 'name' ? 'ascending' : query.ordering === '-name' ? 'descending' : 'none'}><button type="button" onClick={() => sort('name')}>{translate('stock.itemColumn')}{indicator('name')}</button></th><th scope="col">Vendor / part</th><th scope="col" aria-sort={query.ordering === 'quantity_on_hand' ? 'ascending' : query.ordering === '-quantity_on_hand' ? 'descending' : 'none'}><button type="button" onClick={() => sort('quantity_on_hand')}>{translate('stock.onHandColumn')}{indicator('quantity_on_hand')}</button></th><th scope="col">Cost</th><th scope="col">Client price</th><th scope="col">Ordered</th></tr></thead><tbody>{result.results.map((item) => <tr key={item.id}><td data-label="Item"><button id={`stock-row-${item.id}`} className="collection-name" type="button" onClick={() => openRecord(item)}>{item.name}</button></td><td data-label="Vendor / part">{item.vendor_name ?? '—'}{item.vendor_part_number ? ` / ${item.vendor_part_number}` : ''}</td><td data-label="On hand">{item.quantity_on_hand} {item.unit}</td><td data-label="Cost">{item.currency} {item.cost_per_unit}</td><td data-label="Client price">{item.currency} {item.client_price_per_unit}</td><td data-label="Ordered">{item.ordered_on ? formatPlainDate(item.ordered_on) : '—'}</td></tr>)}</tbody></table></div>}
      {phase === 'ready' && result && result.count > result.page_size && <nav className="people-pagination" aria-label="Stock pages"><button className="secondary-button" type="button" disabled={result.page === 1} onClick={() => changeQuery({ page: result.page - 1 })}>{translate('pagination.previous')}</button><span>Page {result.page}</span><button className="secondary-button" type="button" disabled={!result.has_more} onClick={() => changeQuery({ page: result.page + 1 })}>{translate('pagination.next')}</button></nav>}
    </section>
  </>
}

function StockRecord({ item, canManage, onEdit, onMove, onArchive }: { item: StockItem; canManage: boolean; onEdit: () => void; onMove: () => void; onArchive: () => void }) {
  return <div className="operational-record stock-record">
    <p>{item.description || 'No description.'}</p>
    {canManage && <div className="operational-record-actions"><button className="primary-button" type="button" onClick={onMove}>{translate('stock.adjust')}</button><button className="secondary-button" type="button" onClick={onEdit}><Pencil size={15} aria-hidden="true" />{translate('common.edit')}</button><button className="secondary-button danger" type="button" onClick={onArchive}><Archive size={15} aria-hidden="true" />{translate('common.archive')}</button></div>}
    <dl className="record-facts"><div><dt>Vendor</dt><dd>{item.vendor_name ?? '—'}</dd></div><div><dt>Vendor part #</dt><dd>{item.vendor_part_number || '—'}</dd></div><div><dt>On hand</dt><dd>{item.quantity_on_hand} {item.unit}</dd></div><div><dt>Reorder at</dt><dd>{item.reorder_level ? `${item.reorder_level} ${item.unit}` : 'Not set'}</dd></div><div><dt>Cost per {item.unit}</dt><dd>{item.currency} {item.cost_per_unit}</dd></div><div><dt>Client price per {item.unit}</dt><dd>{item.currency} {item.client_price_per_unit}</dd></div><div><dt>Order</dt><dd>{item.order_url ? <a href={item.order_url} target="_blank" rel="noreferrer">{item.order_number || 'Open order'} <ExternalLink size={13} aria-hidden="true" /></a> : item.order_number || '—'}</dd></div><div><dt>Tracking</dt><dd>{item.tracking_url ? <a href={item.tracking_url} target="_blank" rel="noreferrer">{item.tracking_number || 'Open tracking'} <ExternalLink size={13} aria-hidden="true" /></a> : item.tracking_number || '—'}</dd></div></dl>
    <section className="site-location-section" aria-labelledby="stock-history-heading"><div className="section-heading"><h3 id="stock-history-heading">Stock history</h3></div>{item.movements.length === 0 ? <p className="empty-state">No stock changes have been recorded.</p> : <div className="people-table-wrap" role="group" aria-label={translate('stock.historyTable')} tabIndex={0}><table className="people-table stock-history-table"><thead><tr><th>Date</th><th>Change</th><th>After</th><th>Client</th><th>Note</th></tr></thead><tbody>{item.movements.map((entry) => <tr key={entry.id}><td data-label="Date">{formatPlainDate(entry.occurred_at.slice(0, 10))}</td><td data-label="Change">{entry.quantity_change} {item.unit}</td><td data-label="After">{entry.quantity_after} {item.unit}</td><td data-label="Client">{entry.client_name ?? '—'}</td><td data-label="Note">{entry.note || '—'}</td></tr>)}</tbody></table></div>}</section>
  </div>
}

function ItemEditor({ value: initial, vendors, creating, busy, onDirtyChange, cancel, submit }: { value: ItemForm; vendors: StockChoice[]; creating: boolean; busy: boolean; onDirtyChange: (dirty: boolean) => void; cancel: () => void; submit: (value: ItemForm) => Promise<void> }) {
  const [value, setValue] = useState(initial)
  useEffect(() => () => onDirtyChange(false), [onDirtyChange])
  const update = (key: keyof ItemForm, nextValue: string) => {
    const next = { ...value, [key]: nextValue }
    setValue(next)
    onDirtyChange(JSON.stringify(next) !== JSON.stringify(initial))
  }
  const field = (key: keyof ItemForm, label: string, options: { type?: string; step?: string; required?: boolean; wide?: boolean } = {}) => <label className={options.wide ? 'wide-field' : undefined}><span>{label}</span><input type={options.type ?? 'text'} step={options.step} required={options.required ?? false} value={value[key]} onChange={(event) => update(key, event.target.value)} /></label>
  const onSubmit = (event: FormEvent) => { event.preventDefault(); void submit(value) }
  return <form className="record-form record-form-wide stock-item-form operational-record-form" onSubmit={onSubmit}><fieldset className="record-form-section"><legend>Item</legend><div className="form-grid">{field('name', 'Item name', { required: true })}<label><span>Vendor</span><select value={value.vendor_id} onChange={(event) => update('vendor_id', event.target.value)}><option value="">No vendor</option>{vendors.map((vendor) => <option key={vendor.id} value={vendor.id}>{vendor.name}</option>)}</select></label>{field('vendor_part_number', 'Vendor part #')}{field('unit', 'Unit', { required: true })}{field('description', 'Description', { wide: true })}</div></fieldset><fieldset className="record-form-section"><legend>Quantity and pricing</legend><div className="form-grid">{creating && field('initial_quantity', 'Quantity on hand', { type: 'number', step: '0.001' })}{field('reorder_level', 'Reorder at', { type: 'number', step: '0.001' })}{field('currency', 'Currency', { required: true })}{field('cost_per_unit', 'Cost per unit', { type: 'number', step: '0.000001', required: true })}{field('client_price_per_unit', 'Client price per unit', { type: 'number', step: '0.0001', required: true })}</div></fieldset><fieldset className="record-form-section"><legend>Latest order</legend><div className="form-grid">{field('purchase_quantity', 'Purchased quantity', { type: 'number', step: '0.001' })}{field('purchase_price', 'Item price', { type: 'number', step: '0.0001' })}{field('order_total', 'Order total', { type: 'number', step: '0.0001' })}{field('ordered_on', 'Ordered', { type: 'date' })}{field('order_number', 'Order #')}{field('order_url', 'Order link', { type: 'url' })}{field('tracking_number', 'Tracking #')}{field('tracking_url', 'Tracking link', { type: 'url' })}</div></fieldset><div className="form-actions"><button className="primary-button" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save item'}</button><button className="secondary-button" type="button" disabled={busy} onClick={cancel}>{translate('common.cancel')}</button></div></form>
}

function MovementEditor({ item, value: initial, clients, busy, onDirtyChange, cancel, submit }: { item: StockItem; value: MoveForm; clients: StockChoice[]; busy: boolean; onDirtyChange: (dirty: boolean) => void; cancel: () => void; submit: (value: MoveForm) => Promise<void> }) {
  const [value, setValue] = useState(initial)
  useEffect(() => () => onDirtyChange(false), [onDirtyChange])
  const update = (change: Partial<MoveForm>) => {
    const next = { ...value, ...change }
    setValue(next)
    onDirtyChange(JSON.stringify(next) !== JSON.stringify(initial))
  }
  const negative = value.action === 'used' || value.action === 'correction_remove'
  const after = value.quantity ? Number(item.quantity_on_hand) + (negative ? -Number(value.quantity) : Number(value.quantity)) : Number(item.quantity_on_hand)
  const onSubmit = (event: FormEvent) => { event.preventDefault(); void submit(value) }
  return <form className="record-form operational-record-form" onSubmit={onSubmit}><p>{item.quantity_on_hand} {item.unit} currently on hand.</p><div className="form-grid"><label><span>Action</span><select autoFocus value={value.action} onChange={(event) => update({ action: event.target.value as MoveForm['action'] })}><option value="received">Received</option><option value="used">Used at client</option><option value="returned">Returned to stock</option><option value="correction_add">Correction — add</option><option value="correction_remove">Correction — remove</option></select></label><label><span>Quantity ({item.unit})</span><input required type="number" min="0.001" step="0.001" value={value.quantity} onChange={(event) => update({ quantity: event.target.value })} /></label>{value.action === 'used' && <label><span>Client</span><select required value={value.client_id} onChange={(event) => update({ client_id: event.target.value })}><option value="">Choose a client</option>{clients.map((choice) => <option key={choice.id} value={choice.id}>{choice.name}</option>)}</select></label>}<label><span>Date</span><input required type="date" value={value.occurred_on} onChange={(event) => update({ occurred_on: event.target.value })} /></label><label className="wide-field"><span>Note</span><textarea rows={3} maxLength={500} value={value.note} onChange={(event) => update({ note: event.target.value })} /></label></div><p role="status">On hand after this change: <strong>{Number.isFinite(after) ? after.toFixed(3) : item.quantity_on_hand} {item.unit}</strong></p><div className="form-actions"><button className="primary-button" type="submit" disabled={busy || after < 0}>{busy ? 'Saving…' : 'Save change'}</button><button className="secondary-button" type="button" disabled={busy} onClick={cancel}>{translate('common.cancel')}</button></div></form>
}
