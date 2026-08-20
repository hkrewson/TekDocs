import { useEffect, useState } from 'react'
import { translate } from '../i18n/localization'
import type { ClientAsset, HardwareAssignmentChoices, HardwareLifecycleEvent, HardwareProfile, InventoryClient } from './api'
import type { WorkspaceContext } from '../workspaces/api'

const labels: Record<string, string> = { in_stock: 'In stock', in_service: 'In service', repair: 'Repair', retired: 'Retired', disposed: 'Disposed' }

export function HardwareLifecycle({ asset, workspace, client, canManage, onChange }: { asset: ClientAsset; workspace: WorkspaceContext; client: InventoryClient; canManage: boolean; onChange: (hardware: HardwareProfile) => void }) {
  const hardware = asset.hardware
  const [history, setHistory] = useState<HardwareLifecycleEvent[]>([])
  const [choices, setChoices] = useState<HardwareAssignmentChoices>({ people: [], sites: [], locations: [] })
  const [mode, setMode] = useState<'read' | 'edit' | 'assign' | 'dispose'>('read')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState(() => detailsForm(hardware))
  const [assignment, setAssignment] = useState({ person_id: '', site_id: '', location_id: '' })
  const [disposal, setDisposal] = useState({ disposed_on: new Date().toISOString().slice(0, 10), method: 'recycled', reason: '' })

  useEffect(() => {
    // History loading must not touch the form or the mode. This effect re-runs
    // whenever the hardware prop identity changes, so resetting them here meant a
    // background refresh landing mid-edit silently discarded what was being typed
    // and returned the panel to read mode. The form is seeded when edit opens and
    // refreshed after a successful save, which are the moments that actually know
    // the edit is finished.
    if (hardware) client.listHardwareLifecycle(workspace, asset.id)
      .then(setHistory)
      .catch(() => setError('Lifecycle history could not be loaded.'))
  }, [asset.id, client, hardware, workspace])
  if (!hardware) return null
  const disposed = hardware.lifecycle_state === 'disposed'
  async function refresh(next: HardwareProfile) { onChange(next); setForm(detailsForm(next)); setHistory(await client.listHardwareLifecycle(workspace, asset.id)) }
  async function saveDetails(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try { await refresh(await client.updateHardware(workspace, asset.id, { ...form, acquired_on: form.acquired_on || null, warranty_starts_on: form.warranty_starts_on || null, warranty_ends_on: form.warranty_ends_on || null })); setMode('read') }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Hardware details could not be saved.') } finally { setBusy(false) }
  }
  async function startAssignment() {
    setError(null)
    try { setChoices(await client.assignmentChoices(workspace, asset.id)); setMode('assign') } catch { setError('Assignment choices could not be loaded.') }
  }
  async function saveAssignment(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try { const values = Object.fromEntries(Object.entries(assignment).map(([key, value]) => [key, value || null])); await refresh(await client.assignHardware(workspace, asset.id, values)); setMode('read') }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'The assignment could not be saved.') } finally { setBusy(false) }
  }
  async function unassign() {
    setBusy(true); setError(null)
    try { await refresh(await client.unassignHardware(workspace, asset.id)) } catch (caught) { setError(caught instanceof Error ? caught.message : 'The assignment could not be cleared.') } finally { setBusy(false) }
  }
  async function dispose(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try { await refresh(await client.disposeHardware(workspace, asset.id, disposal)); setMode('read') } catch (caught) { setError(caught instanceof Error ? caught.message : 'The asset could not be disposed.') } finally { setBusy(false) }
  }

  return <section className="hardware-lifecycle" aria-labelledby="hardware-heading">
    <div className="section-heading"><div><h3 id="hardware-heading">Hardware lifecycle</h3><p>Current identity, custody, warranty, and retained history.</p></div><span className="lifecycle-state">{labels[hardware.lifecycle_state]}</span></div>
    {error && <div className="form-message error" role="alert">{error}</div>}
    {mode === 'read' && <dl className="inventory-provenance"><div><dt>Serial number</dt><dd>{hardware.serial_number || 'Not recorded'}</dd></div><div><dt>Asset tag</dt><dd>{hardware.asset_tag || 'Not recorded'}</dd></div><div><dt>Acquired</dt><dd>{hardware.acquired_on || 'Not recorded'}{hardware.acquisition_method ? ` · ${hardware.acquisition_method}` : ''}</dd></div><div><dt>Warranty</dt><dd>{hardware.warranty_ends_on ? `Through ${hardware.warranty_ends_on}` : 'Not recorded'}{hardware.warranty_provider ? ` · ${hardware.warranty_provider}` : ''}</dd></div><div><dt>Assigned to</dt><dd>{[hardware.assignment.person_name, hardware.assignment.location_name, hardware.assignment.site_name].filter(Boolean).join(' · ') || 'Unassigned'}</dd></div>{disposed && <div><dt>Disposed</dt><dd>{hardware.disposed_on} · {hardware.disposal_method}</dd></div>}</dl>}
    {canManage && !disposed && mode === 'read' && <div className="form-actions lifecycle-actions"><button type="button" className="secondary-button" onClick={() => { setForm(detailsForm(hardware)); setMode('edit') }}>{translate('inventory.editDetails')}</button><button type="button" className="secondary-button" onClick={() => void startAssignment()}>{translate('inventory.assign')}</button>{hardware.assignment.assigned_at && <button type="button" className="secondary-button" disabled={busy} onClick={() => void unassign()}>{translate('inventory.unassign')}</button>}<button type="button" className="danger-button" onClick={() => setMode('dispose')}>{translate('inventory.dispose')}</button></div>}
    {mode === 'edit' && <form className="hardware-form" onSubmit={(event) => void saveDetails(event)}><div className="field-grid"><Field label="Serial number" value={form.serial_number} onChange={(value) => setForm({ ...form, serial_number: value })} /><Field label="Asset tag" value={form.asset_tag} onChange={(value) => setForm({ ...form, asset_tag: value })} /><label><span>Lifecycle state</span><select value={form.lifecycle_state} onChange={(event) => setForm({ ...form, lifecycle_state: event.target.value as HardwareProfile['lifecycle_state'] })}>{['in_stock', 'in_service', 'repair', 'retired'].map((value) => <option key={value} value={value}>{labels[value]}</option>)}</select></label><Field label="Acquired on" type="date" value={form.acquired_on} onChange={(value) => setForm({ ...form, acquired_on: value })} /><label><span>Acquisition method</span><select value={form.acquisition_method} onChange={(event) => setForm({ ...form, acquisition_method: event.target.value })}><option value="">Not recorded</option>{['purchase', 'lease', 'rental', 'transfer', 'donation', 'other'].map((value) => <option key={value}>{value}</option>)}</select></label><Field label="Acquisition reference" value={form.acquisition_reference} onChange={(value) => setForm({ ...form, acquisition_reference: value })} /><Field label="Warranty provider" value={form.warranty_provider} onChange={(value) => setForm({ ...form, warranty_provider: value })} /><Field label="Warranty starts" type="date" value={form.warranty_starts_on} onChange={(value) => setForm({ ...form, warranty_starts_on: value })} /><Field label="Warranty ends" type="date" value={form.warranty_ends_on} onChange={(value) => setForm({ ...form, warranty_ends_on: value })} /><Field label="Warranty reference" value={form.warranty_reference} onChange={(value) => setForm({ ...form, warranty_reference: value })} /></div><Actions busy={busy} primary="Save details" cancel={() => setMode('read')} /></form>}
    {mode === 'assign' && <form className="hardware-form" onSubmit={(event) => void saveAssignment(event)}><h4>Assign hardware</h4><div className="field-grid"><Choice label="Person" value={assignment.person_id} items={choices.people} onChange={(value) => setAssignment({ ...assignment, person_id: value })} /><Choice label="Site" value={assignment.site_id} items={choices.sites} onChange={(value) => setAssignment({ ...assignment, site_id: value, location_id: '' })} /><Choice label="Location" value={assignment.location_id} items={choices.locations.filter((item) => !assignment.site_id || item.site_id === assignment.site_id)} onChange={(value) => setAssignment({ ...assignment, location_id: value })} /></div><Actions busy={busy || !Object.values(assignment).some(Boolean)} primary="Save assignment" cancel={() => setMode('read')} /></form>}
    {mode === 'dispose' && <form className="hardware-form disposal-form" onSubmit={(event) => void dispose(event)}><h4>Dispose asset</h4><p>This clears its assignment and permanently closes its ordinary lifecycle.</p><div className="field-grid"><Field label="Disposed on" type="date" required value={disposal.disposed_on} onChange={(value) => setDisposal({ ...disposal, disposed_on: value })} /><label><span>Method</span><select value={disposal.method} onChange={(event) => setDisposal({ ...disposal, method: event.target.value })}>{['recycled', 'returned', 'sold', 'donated', 'destroyed', 'lost', 'other'].map((value) => <option key={value}>{value}</option>)}</select></label><Field label="Reason" value={disposal.reason} onChange={(value) => setDisposal({ ...disposal, reason: value })} /></div><Actions busy={busy} primary="Confirm disposal" danger cancel={() => setMode('read')} /></form>}
    <div className="lifecycle-history"><h4>Lifecycle history</h4>{history.length === 0 ? <p className="empty-state">No lifecycle events are available.</p> : <ol>{history.map((item) => <li key={item.id}><strong>{item.event_type.replaceAll('_', ' ')}</strong><span>{[item.person_name, item.location_name, item.site_name].filter(Boolean).join(' · ')}</span><time dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleString()}</time></li>)}</ol>}</div>
  </section>
}

function Field({ label, value, onChange, type = 'text', required = false }: { label: string; value: string; onChange: (value: string) => void; type?: string; required?: boolean }) { return <label><span>{label}</span><input type={type} required={required} value={value} onChange={(event) => onChange(event.target.value)} /></label> }
function Choice({ label, value, items, onChange }: { label: string; value: string; items: Array<{ id: string; name: string }>; onChange: (value: string) => void }) { return <label><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}><option value="">None</option>{items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label> }
function Actions({ busy, primary, cancel, danger = false }: { busy: boolean; primary: string; cancel: () => void; danger?: boolean }) { return <div className="form-actions"><button className={danger ? 'danger-button' : 'primary-button'} disabled={busy}>{primary}</button><button type="button" className="secondary-button" onClick={cancel}>{translate('common.cancel')}</button></div> }
function detailsForm(hardware: HardwareProfile | null) { const initialState: HardwareProfile['lifecycle_state'] = 'in_stock'; return { serial_number: hardware?.serial_number ?? '', asset_tag: hardware?.asset_tag ?? '', lifecycle_state: hardware?.lifecycle_state ?? initialState, acquired_on: hardware?.acquired_on ?? '', acquisition_method: hardware?.acquisition_method ?? '', acquisition_reference: hardware?.acquisition_reference ?? '', warranty_provider: hardware?.warranty_provider ?? '', warranty_starts_on: hardware?.warranty_starts_on ?? '', warranty_ends_on: hardware?.warranty_ends_on ?? '', warranty_reference: hardware?.warranty_reference ?? '' } }
