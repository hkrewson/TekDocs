import { useEffect, useState } from 'react'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { ClientAsset, HardwareAssignmentChoices, InventoryClient } from './api'
import type { WorkspaceContext } from '../workspaces/api'

export function AssetQuickAssignment({ asset, workspace, client, onChange, onCancel }: {
  asset: ClientAsset; workspace: WorkspaceContext; client: InventoryClient
  onChange: (asset: ClientAsset) => void; onCancel: () => void
}) {
  const [choices, setChoices] = useState<HardwareAssignmentChoices | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [reload, setReload] = useState(0)
  const [draft, setDraft] = useState({ person_id: '', site_id: '', location_id: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const hasAssignment = Object.values(draft).some(Boolean)
  const attempt = useUnsavedChanges(hasAssignment, busy, onCancel, true)
  useEffect(() => {
    let active = true
    client.assignmentChoices(workspace, asset.id).then((value) => { if (active) setChoices(value) }).catch(() => { if (active) setLoadFailed(true) })
    return () => { active = false }
  }, [asset.id, workspace, client, reload])
  async function save() {
    if (busy || !choices || !hasAssignment) return
    setBusy(true); setError(false)
    try {
      const hardware = await client.assignHardware(workspace, asset.id, {
        person_id: draft.person_id || null, site_id: draft.site_id || null, location_id: draft.location_id || null,
      })
      onChange({ ...asset, hardware }); onCancel()
    } catch { setError(true) }
    finally { setBusy(false) }
  }
  return <form className="asset-quick-assignment" aria-label={translate('collections.assignHardware')} onSubmit={(event) => { event.preventDefault(); void save() }}>
    <h3>{translate('collections.assignHardware')}</h3>
    <p>{translate('collections.assignmentHelp')}</p>
    {!choices && !loadFailed && <p role="status">{translate('collections.assignmentLoading')}</p>}
    {loadFailed && <p role="alert">{translate('collections.assignmentLoadFailed')} <button type="button" onClick={() => { setLoadFailed(false); setReload(reload + 1) }}>{translate('collections.retry')}</button></p>}
    {choices && <fieldset disabled={busy}>
      <Choice label={translate('collections.person')} value={draft.person_id} items={choices.people} onChange={(person_id) => setDraft({ ...draft, person_id })} />
      <Choice label={translate('collections.site')} value={draft.site_id} items={choices.sites} onChange={(site_id) => setDraft({ ...draft, site_id, location_id: '' })} />
      <Choice label={translate('collections.location')} value={draft.location_id} items={choices.locations.filter((item) => !draft.site_id || item.site_id === draft.site_id)} onChange={(location_id) => setDraft({ ...draft, location_id, site_id: choices.locations.find((item) => item.id === location_id)?.site_id ?? draft.site_id })} />
    </fieldset>}
    {error && <p role="alert">{translate('collections.assignmentFailed')}</p>}
    <div className="form-actions"><button type="submit" className="primary-button" disabled={busy || !choices || !hasAssignment}>{translate('collections.saveAssignment')}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => attempt(onCancel)}>{translate('common.cancel')}</button></div>
  </form>
}

function Choice({ label, value, items, onChange }: { label: string; value: string; items: Array<{ id: string; name: string }>; onChange: (value: string) => void }) {
  return <label>{label}<select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}><option value="">{translate('collections.noAssignmentChoice')}</option>{items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
}
