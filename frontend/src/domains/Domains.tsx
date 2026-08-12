import { Plus } from 'lucide-react'
import { useEffect, useState } from 'react'

import type { WorkspaceContext } from '../workspaces/api'
import type { DomainDraft, DomainsClient, RegisteredDomain } from './api'

const EMPTY: DomainDraft = {
  name: '', registrar_id: null, registration_date: null, expiration_date: null,
  renewal_mode: 'manual', owner_id: null, status: 'active', notes: '',
}

export function Domains({ workspace, client }: { workspace: WorkspaceContext | null; client: DomainsClient }) {
  const [domains, setDomains] = useState<RegisteredDomain[]>([])
  const [draft, setDraft] = useState<DomainDraft>(EMPTY)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    void client.list(workspace, controller.signal).then(setDomains).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Domains could not be loaded.')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [client, workspace])

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const created = await client.create(workspace, draft)
      setDomains((current) => [...current, created].sort((a, b) => a.name.localeCompare(b.name)))
      setDraft(EMPTY)
      setOpen(false)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The domain could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  return <>
    <header className="page-header"><div><h1>Domains</h1><p>Registration ownership, renewal dates, and responsible staff for this workspace.</p></div><button type="button" className="primary-button" onClick={() => setOpen(true)}><Plus size={16} /> Add domain</button></header>
    {error && <p role="alert" className="form-error">{error}</p>}
    {open && <section className="content-section" aria-labelledby="domain-form-title">
      <div className="section-heading"><div><h2 id="domain-form-title">New registered domain</h2><p>Enter the known registration details. Automated observations arrive in later monitoring slices.</p></div></div>
      <div className="compliance-risk-form">
        <label><span>Domain name</span><input autoFocus value={draft.name} placeholder="example.com" onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
        <label><span>Status</span><select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value as DomainDraft['status'] })}><option value="active">Active</option><option value="pending">Pending</option><option value="expired">Expired</option><option value="transferred">Transferred</option></select></label>
        <label><span>Registered on</span><input type="date" value={draft.registration_date ?? ''} onChange={(event) => setDraft({ ...draft, registration_date: event.target.value || null })} /></label>
        <label><span>Expires on</span><input type="date" value={draft.expiration_date ?? ''} onChange={(event) => setDraft({ ...draft, expiration_date: event.target.value || null })} /></label>
        <label><span>Renewal</span><select value={draft.renewal_mode} onChange={(event) => setDraft({ ...draft, renewal_mode: event.target.value as DomainDraft['renewal_mode'] })}><option value="manual">Manual</option><option value="auto">Automatic</option><option value="external">Managed externally</option></select></label>
        <label className="wide-field"><span>Notes (Markdown)</span><textarea rows={3} value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} /></label>
        <div className="form-actions wide-field"><button type="button" className="primary-button" disabled={saving || !draft.name.trim()} onClick={() => { void save() }}>{saving ? 'Saving…' : 'Save domain'}</button><button type="button" className="secondary-button" onClick={() => setOpen(false)}>Cancel</button></div>
      </div>
    </section>}
    <section className="content-section" aria-labelledby="domain-list-title">
      <div className="section-heading"><div><h2 id="domain-list-title">Registered domains</h2><p>Only domains owned by the active MSP or organization workspace appear here.</p></div><span>{domains.length}</span></div>
      {loading ? <p role="status">Loading domains…</p> : domains.length === 0 ? <p className="empty-state">No registered domains are recorded in this workspace.</p> : <div className="network-table-wrap"><table className="network-table"><thead><tr><th>Domain</th><th>Status</th><th>Renewal</th><th>Expiration</th><th>Review</th><th>Owner</th></tr></thead><tbody>{domains.map((domain) => <tr key={domain.id}><td><strong>{domain.name}</strong><small>{domain.registrar ?? 'Registrar not recorded'}</small></td><td>{domain.status}</td><td>{domain.renewal_mode}</td><td>{domain.expiration_date ?? 'Not recorded'}</td><td>{domain.review_state}</td><td>{domain.owner ?? 'Unassigned'}</td></tr>)}</tbody></table></div>}
    </section>
  </>
}
