import { useEffect, useMemo, useState } from 'react'
import { Archive, ExternalLink, Plus } from 'lucide-react'
import type { FormEvent } from 'react'
import { formatPlainDate, translate } from '../i18n/localization'
import type { StockChoice, StockClient, StockItem } from './api'

type ItemForm = {
  name: string; description: string; vendor_id: string; vendor_part_number: string; unit: string
  initial_quantity: string; reorder_level: string; currency: string; cost_per_unit: string
  client_price_per_unit: string; purchase_quantity: string; purchase_price: string; order_total: string
  order_number: string; order_url: string; ordered_on: string; tracking_number: string; tracking_url: string
}
type MoveForm = { action: 'received' | 'used' | 'returned' | 'correction_add' | 'correction_remove'; quantity: string; client_id: string; note: string; occurred_on: string }

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

export function Stock({ client }: { client: StockClient }) {
  const [items, setItems] = useState<StockItem[]>([])
  const [vendors, setVendors] = useState<StockChoice[]>([])
  const [clients, setClients] = useState<StockChoice[]>([])
  const [canManage, setCanManage] = useState(false)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [editor, setEditor] = useState<'none' | 'item' | 'move'>('none')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<ItemForm>(emptyItem())
  const [move, setMove] = useState<MoveForm>(emptyMove())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    client.list(controller.signal).then((result) => { setItems(result.results); setVendors(result.vendors); setClients(result.clients); setCanManage(result.can_manage); setPhase('ready') }).catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client])

  const visible = useMemo(() => {
    const value = query.trim().toLowerCase()
    return value ? items.filter((item) => [item.name, item.vendor_name ?? '', item.vendor_part_number, item.description].some((field) => field.toLowerCase().includes(value))) : items
  }, [items, query])
  const selected = items.find((item) => item.id === selectedId) ?? visible[0]

  async function saveItem(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try {
      const record = editingId ? await client.update(editingId, payload(form, false)) : await client.create(payload(form, true))
      setItems((current) => editingId ? current.map((item) => item.id === record.id ? record : item) : [...current, record].sort((a, b) => a.name.localeCompare(b.name)))
      setSelectedId(record.id); setEditor('none'); setEditingId(null)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The stock item could not be saved.') }
    finally { setBusy(false) }
  }

  async function saveMovement(event: FormEvent) {
    event.preventDefault(); if (!selected) return
    const negative = move.action === 'used' || move.action === 'correction_remove'
    const movement_type = move.action.startsWith('correction') ? 'correction' : move.action
    setBusy(true); setError(null)
    try {
      const record = await client.move(selected.id, { movement_type, quantity_change: `${negative ? '-' : ''}${move.quantity}`, client_id: move.action === 'used' ? move.client_id || null : null, note: move.note, occurred_at: `${move.occurred_on}T12:00:00Z` })
      setItems((current) => current.map((item) => item.id === record.id ? record : item)); setEditor('none')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The stock quantity could not be changed.') }
    finally { setBusy(false) }
  }

  async function archiveSelected() {
    if (!selected || !window.confirm(`Archive ${selected.name}? Its stock history will be retained.`)) return
    setBusy(true); setError(null)
    try { await client.archive(selected.id); setItems((current) => current.filter((item) => item.id !== selected.id)); setSelectedId(null) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'The stock item could not be archived.') }
    finally { setBusy(false) }
  }

  return <>
    <header className="page-header"><div><h1>Stock</h1><p>Supplies kept by the MSP for use at any client.</p></div>{canManage && <button className="primary-button" type="button" onClick={() => { setForm(emptyItem()); setEditingId(null); setEditor('item') }}><Plus size={16} />{translate('stock.newItem')}</button>}</header>
    {error && <div className="form-message error" role="alert">{error}</div>}
    {phase === 'loading' && <section className="content-section" role="status">Loading stock…</section>}
    {phase === 'error' && <section className="content-section workspace-error" role="alert"><h2>Stock unavailable</h2><p>Stock could not be loaded.</p></section>}
    {phase === 'ready' && <><section className="content-section stock-list"><div className="section-heading"><label><span>Search</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Item, vendor, part number, or description" /></label><span>{visible.length} {visible.length === 1 ? 'item' : 'items'}</span></div>{visible.length === 0 ? <p className="empty-state">{items.length ? 'No stock matches this search.' : 'No stock items have been created.'}</p> : <div className="table-scroll" role="group" aria-label={translate('stock.itemsTable')} tabIndex={0}><table><thead><tr><th>Item</th><th>Vendor / part</th><th>On hand</th><th>Cost</th><th>Client price</th><th>Ordered</th></tr></thead><tbody>{visible.map((item) => <tr key={item.id} className={selected?.id === item.id ? 'selected-row' : undefined} onClick={() => setSelectedId(item.id)}><td><button className="row-action" type="button" onClick={() => setSelectedId(item.id)}>{item.name}</button></td><td>{item.vendor_name ?? '—'}{item.vendor_part_number ? ` / ${item.vendor_part_number}` : ''}</td><td>{item.quantity_on_hand} {item.unit}</td><td>{item.currency} {item.cost_per_unit}</td><td>{item.currency} {item.client_price_per_unit}</td><td>{item.ordered_on ? formatPlainDate(item.ordered_on) : '—'}</td></tr>)}</tbody></table></div>}</section>
      {selected && <section className="content-section stock-detail"><div className="section-heading"><div><h2>{selected.name}</h2><p>{selected.description || 'No description.'}</p></div>{canManage && <div className="page-header-actions"><button className="secondary-button" type="button" onClick={() => { setMove(emptyMove()); setEditor('move') }}>{translate('stock.adjust')}</button><button className="secondary-button" type="button" onClick={() => { setForm(itemForm(selected)); setEditingId(selected.id); setEditor('item') }}>{translate('common.edit')}</button><button className="icon-button" type="button" aria-label={`Archive ${selected.name}`} disabled={busy} onClick={() => { void archiveSelected() }}><Archive size={16} /></button></div>}</div><dl className="inventory-provenance"><div><dt>Vendor</dt><dd>{selected.vendor_name ?? '—'}</dd></div><div><dt>Vendor part #</dt><dd>{selected.vendor_part_number || '—'}</dd></div><div><dt>On hand</dt><dd>{selected.quantity_on_hand} {selected.unit}</dd></div><div><dt>Reorder at</dt><dd>{selected.reorder_level ? `${selected.reorder_level} ${selected.unit}` : 'Not set'}</dd></div><div><dt>Cost per {selected.unit}</dt><dd>{selected.currency} {selected.cost_per_unit}</dd></div><div><dt>Client price per {selected.unit}</dt><dd>{selected.currency} {selected.client_price_per_unit}</dd></div><div><dt>Order</dt><dd>{selected.order_url ? <a href={selected.order_url} target="_blank" rel="noreferrer">{selected.order_number || 'Open order'} <ExternalLink size={13} /></a> : selected.order_number || '—'}</dd></div><div><dt>Tracking</dt><dd>{selected.tracking_url ? <a href={selected.tracking_url} target="_blank" rel="noreferrer">{selected.tracking_number || 'Open tracking'} <ExternalLink size={13} /></a> : selected.tracking_number || '—'}</dd></div></dl><div className="section-heading"><h3>Stock history</h3></div>{selected.movements.length === 0 ? <p className="empty-state">No stock changes have been recorded.</p> : <div className="table-scroll" role="group" aria-label={translate('stock.historyTable')} tabIndex={0}><table><thead><tr><th>Date</th><th>Change</th><th>After</th><th>Client</th><th>Note</th></tr></thead><tbody>{selected.movements.map((entry) => <tr key={entry.id}><td>{formatPlainDate(entry.occurred_at.slice(0, 10))}</td><td>{entry.quantity_change} {selected.unit}</td><td>{entry.quantity_after} {selected.unit}</td><td>{entry.client_name ?? '—'}</td><td>{entry.note || '—'}</td></tr>)}</tbody></table></div>}</section>}
    </>}
    {editor === 'item' && <ItemEditor value={form} setValue={setForm} vendors={vendors} creating={!editingId} busy={busy} cancel={() => setEditor('none')} submit={(event) => { void saveItem(event) }} />}
    {editor === 'move' && selected && <MovementEditor item={selected} value={move} setValue={setMove} clients={clients} busy={busy} cancel={() => setEditor('none')} submit={(event) => { void saveMovement(event) }} />}
  </>
}

function ItemEditor({ value, setValue, vendors, creating, busy, cancel, submit }: { value: ItemForm; setValue: (value: ItemForm) => void; vendors: StockChoice[]; creating: boolean; busy: boolean; cancel: () => void; submit: (event: FormEvent) => void }) {
  const field = (key: keyof ItemForm, label: string, options: { type?: string; step?: string; required?: boolean; wide?: boolean } = {}) => <label className={options.wide ? 'wide-field' : undefined}><span>{label}</span><input type={options.type ?? 'text'} step={options.step} required={options.required ?? false} value={value[key]} onChange={(event) => setValue({ ...value, [key]: event.target.value })} /></label>
  return <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="stock-item-title"><form className="record-form" onSubmit={submit}><div className="section-heading"><h2 id="stock-item-title">{creating ? 'New stock item' : 'Edit stock item'}</h2></div><fieldset className="record-form-section"><legend>Item</legend><div className="form-grid">{field('name', 'Item name', { required: true })}<label><span>Vendor</span><select value={value.vendor_id} onChange={(event) => setValue({ ...value, vendor_id: event.target.value })}><option value="">No vendor</option>{vendors.map((vendor) => <option key={vendor.id} value={vendor.id}>{vendor.name}</option>)}</select></label>{field('vendor_part_number', 'Vendor part #')}{field('unit', 'Unit', { required: true })}{field('description', 'Description', { wide: true })}</div></fieldset><fieldset className="record-form-section"><legend>Quantity and pricing</legend><div className="form-grid">{creating && field('initial_quantity', 'Quantity on hand', { type: 'number', step: '0.001' })}{field('reorder_level', 'Reorder at', { type: 'number', step: '0.001' })}{field('currency', 'Currency', { required: true })}{field('cost_per_unit', 'Cost per unit', { type: 'number', step: '0.000001', required: true })}{field('client_price_per_unit', 'Client price per unit', { type: 'number', step: '0.0001', required: true })}</div></fieldset><fieldset className="record-form-section"><legend>Latest order</legend><div className="form-grid">{field('purchase_quantity', 'Purchased quantity', { type: 'number', step: '0.001' })}{field('purchase_price', 'Item price', { type: 'number', step: '0.0001' })}{field('order_total', 'Order total', { type: 'number', step: '0.0001' })}{field('ordered_on', 'Ordered', { type: 'date' })}{field('order_number', 'Order #')}{field('order_url', 'Order link', { type: 'url' })}{field('tracking_number', 'Tracking #')}{field('tracking_url', 'Tracking link', { type: 'url' })}</div></fieldset><div className="form-actions"><button className="primary-button" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save item'}</button><button className="secondary-button" type="button" disabled={busy} onClick={cancel}>{translate('common.cancel')}</button></div></form></section>
}

function MovementEditor({ item, value, setValue, clients, busy, cancel, submit }: { item: StockItem; value: MoveForm; setValue: (value: MoveForm) => void; clients: StockChoice[]; busy: boolean; cancel: () => void; submit: (event: FormEvent) => void }) {
  const negative = value.action === 'used' || value.action === 'correction_remove'
  const result = value.quantity ? Number(item.quantity_on_hand) + (negative ? -Number(value.quantity) : Number(value.quantity)) : Number(item.quantity_on_hand)
  return <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="stock-move-title"><form className="record-form" onSubmit={submit}><div className="section-heading"><div><h2 id="stock-move-title">Adjust {item.name}</h2><p>{item.quantity_on_hand} {item.unit} currently on hand.</p></div></div><div className="form-grid"><label><span>Action</span><select autoFocus value={value.action} onChange={(event) => setValue({ ...value, action: event.target.value as MoveForm['action'] })}><option value="received">Received</option><option value="used">Used at client</option><option value="returned">Returned to stock</option><option value="correction_add">Correction — add</option><option value="correction_remove">Correction — remove</option></select></label><label><span>Quantity ({item.unit})</span><input required type="number" min="0.001" step="0.001" value={value.quantity} onChange={(event) => setValue({ ...value, quantity: event.target.value })} /></label>{value.action === 'used' && <label><span>Client</span><select required value={value.client_id} onChange={(event) => setValue({ ...value, client_id: event.target.value })}><option value="">Choose a client</option>{clients.map((choice) => <option key={choice.id} value={choice.id}>{choice.name}</option>)}</select></label>}<label><span>Date</span><input required type="date" value={value.occurred_on} onChange={(event) => setValue({ ...value, occurred_on: event.target.value })} /></label><label className="wide-field"><span>Note</span><textarea rows={3} maxLength={500} value={value.note} onChange={(event) => setValue({ ...value, note: event.target.value })} /></label></div><p role="status">On hand after this change: <strong>{Number.isFinite(result) ? result.toFixed(3) : item.quantity_on_hand} {item.unit}</strong></p><div className="form-actions"><button className="primary-button" type="submit" disabled={busy || result < 0}>{busy ? 'Saving…' : 'Save change'}</button><button className="secondary-button" type="button" disabled={busy} onClick={cancel}>{translate('common.cancel')}</button></div></form></section>
}
