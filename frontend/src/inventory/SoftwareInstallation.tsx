import { useState } from 'react'
import type { ClientAsset, InventoryClient, SoftwareInstallation as Installation } from './api'
import type { WorkspaceContext } from '../workspaces/api'

export function SoftwareInstallation({ asset, workspace, client, canManage, onChange }: { asset: ClientAsset; workspace: WorkspaceContext; client: InventoryClient; canManage: boolean; onChange: (installation: Installation) => void }) {
  const installation = asset.software_installation
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState(() => values(installation))
  if (!installation) return null

  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try {
      const updated = await client.updateSoftwareInstallation(workspace, asset.id, {
        ...form,
        installed_on: form.installed_on || null,
        last_verified_on: form.last_verified_on || null,
      })
      onChange(updated); setForm(values(updated)); setEditing(false)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Installation details could not be saved.') }
    finally { setBusy(false) }
  }

  return <section className="hardware-lifecycle" aria-labelledby="software-installation-heading">
    <div className="section-heading"><div><h3 id="software-installation-heading">Software installation</h3><p>Deployment version, status, and verification state.</p></div><span className="lifecycle-state">{installation.status}</span></div>
    {error && <div className="form-message error" role="alert">{error}</div>}
    {!editing && <><dl className="inventory-provenance"><div><dt>Installed version</dt><dd>{installation.installed_version || 'Not recorded'}</dd></div><div><dt>Installed on</dt><dd>{installation.installed_on || 'Not recorded'}</dd></div><div><dt>Last verified</dt><dd>{installation.last_verified_on || 'Not recorded'}</dd></div><div><dt>Site</dt><dd>{installation.site_name || 'Organization-wide or remote'}</dd></div></dl>{canManage && installation.status !== 'uninstalled' && <button type="button" className="secondary-button" onClick={() => setEditing(true)}>Edit installation</button>}</>}
    {editing && <form className="hardware-form" onSubmit={(event) => void save(event)}><div className="field-grid"><label><span>Status</span><select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as Installation['status'] })}>{['planned', 'installed', 'suspended', 'uninstalled'].map((status) => <option key={status}>{status}</option>)}</select></label><Field label="Installed version" value={form.installed_version} onChange={(value) => setForm({ ...form, installed_version: value })} /><Field label="Installed on" type="date" value={form.installed_on} onChange={(value) => setForm({ ...form, installed_on: value })} /><Field label="Last verified" type="date" value={form.last_verified_on} onChange={(value) => setForm({ ...form, last_verified_on: value })} /></div><div className="form-actions"><button className="primary-button" disabled={busy || (form.status === 'installed' && !form.installed_on)}>{busy ? 'Saving…' : 'Save installation'}</button><button type="button" className="secondary-button" onClick={() => setEditing(false)}>Cancel</button></div></form>}
  </section>
}

function Field({ label, value, onChange, type = 'text' }: { label: string; value: string; onChange: (value: string) => void; type?: string }) { return <label><span>{label}</span><input type={type} value={value} onChange={(event) => onChange(event.target.value)} /></label> }
function values(installation: Installation | null): { status: Installation['status']; installed_version: string; installed_on: string; last_verified_on: string } {
  return { status: installation?.status ?? 'planned', installed_version: installation?.installed_version ?? '', installed_on: installation?.installed_on ?? '', last_verified_on: installation?.last_verified_on ?? '' }
}
