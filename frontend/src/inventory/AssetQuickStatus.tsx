import { AssetQuickAssignment } from './AssetQuickAssignment'
import { useState } from 'react'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { ClientAsset, HardwareProfile, InventoryClient } from './api'
import type { WorkspaceContext } from '../workspaces/api'

export function AssetQuickStatus({ asset, workspace, client, onChange }: { asset: ClientAsset; workspace: WorkspaceContext; client: InventoryClient; onChange: (asset: ClientAsset) => void }) {
  const current = asset.hardware?.lifecycle_state ?? 'in_stock'
  const [assigning, setAssigning] = useState(false)
  const [status, setStatus] = useState(current)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const attempt = useUnsavedChanges(!assigning && status !== current, busy, () => setStatus(current), !assigning && status !== current)
  if (!asset.hardware || current === 'disposed') return null
  async function save() {
    setBusy(true); setError(false)
    try { const hardware = await client.updateHardware(workspace, asset.id, { lifecycle_state: status }); onChange({ ...asset, hardware }) }
    catch { setError(true) }
    finally { setBusy(false) }
  }
  if (assigning) return <AssetQuickAssignment asset={asset} workspace={workspace} client={client} onChange={(updated) => { setStatus(updated.hardware?.lifecycle_state ?? current); onChange(updated) }} onCancel={() => setAssigning(false)} />
  return <><form className="asset-quick-status" onSubmit={(event) => { event.preventDefault(); void save() }}>
    <label>{translate('collections.quickStatus')}<select aria-label={translate('collections.quickStatus')} disabled={busy} value={status} onChange={(event) => setStatus(event.target.value as HardwareProfile['lifecycle_state'])}>{['in_stock', 'in_service', 'repair', 'retired'].map((value) => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select></label>
    {error && <p role="alert">{translate('collections.statusFailed')}</p>}
    <button type="submit" className="secondary-button" disabled={busy || status === current}>{translate('collections.saveStatus')}</button>
  </form><button type="button" className="secondary-button" disabled={busy} onClick={() => attempt(() => { setStatus(current); setError(false); setAssigning(true) })}>{translate('collections.assignHardware')}</button></>
}
