import { useEffect, useState } from 'react'
import { ExternalLink, KeyRound, Plus, Search, Trash2 } from 'lucide-react'

import type { WorkspaceContext } from '../workspaces/api'
import type { CredentialReference, CredentialReferenceDraft, CredentialReferencesClient } from './api'

const EMPTY_DRAFT: CredentialReferenceDraft = { title: '', provider: 'onepassword', reference_url: '' }

export function CredentialReferences({ workspace, client }: { workspace: WorkspaceContext | null; client: CredentialReferencesClient }) {
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [references, setReferences] = useState<CredentialReference[]>([])
  const [canManage, setCanManage] = useState(false)
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<CredentialReference | 'new' | null>(null)
  const [draft, setDraft] = useState(EMPTY_DRAFT)
  const [archiving, setArchiving] = useState<CredentialReference | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    client.list(workspace, query, controller.signal)
      .then((result) => { setReferences(result.results); setCanManage(result.can_manage); setPhase('ready') })
      .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client, query, workspace])

  function startEdit(reference: CredentialReference | 'new') {
    setEditing(reference)
    setDraft(reference === 'new' ? EMPTY_DRAFT : { title: reference.title, provider: 'onepassword', reference_url: '' })
    setError(null)
  }

  async function save() {
    if (!editing) return
    setSaving(true)
    setError(null)
    try {
      const saved = editing === 'new'
        ? await client.create(workspace, draft)
        : await client.update(workspace, editing.id, { title: draft.title, ...(draft.reference_url ? { reference_url: draft.reference_url } : {}) })
      setReferences((current) => editing === 'new' ? [...current, saved].sort((a, b) => a.title.localeCompare(b.title)) : current.map((item) => item.id === saved.id ? saved : item))
      setEditing(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The reference could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  async function archive() {
    if (!archiving) return
    setSaving(true)
    setError(null)
    try {
      await client.archive(workspace, archiving.id)
      setReferences((current) => current.filter((item) => item.id !== archiving.id))
      setArchiving(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The reference could not be archived.')
    } finally {
      setSaving(false)
    }
  }

  return <>
    <header className="page-header"><div><h1>Credential references</h1><p>Pointers to credentials protected by 1Password. TekDocs never stores, retrieves, or displays the credential value.</p></div>{canManage && <button className="primary-button" type="button" onClick={() => startEdit('new')}><Plus size={16} />New reference</button>}</header>
    {error && <div className="form-message error" role="alert">{error}</div>}
    <section className="content-section credential-reference-section" aria-busy={phase === 'loading'}>
      <div className="credential-reference-boundary"><KeyRound size={18} aria-hidden="true" /><div><strong>1Password remains the security boundary</strong><p>Opening a reference hands off to 1Password, which requires your own vault access and unlock. Public share links are not accepted.</p></div></div>
      <label className="credential-reference-search"><span>Search titles</span><div><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a credential reference" /></div></label>
      {phase === 'loading' && <p className="empty-state" role="status">Loading credential references…</p>}
      {phase === 'error' && <p className="empty-state" role="alert">Credential references are unavailable.</p>}
      {phase === 'ready' && references.length === 0 && <p className="empty-state">{query ? 'No credential-reference titles match this search.' : 'No credential references have been added to this workspace.'}</p>}
      {phase === 'ready' && references.length > 0 && <ul className="credential-reference-list">{references.map((reference) => <li key={reference.id}><div><strong>{reference.title}</strong><span>{reference.provider_label} · Updated {new Date(reference.updated_at).toLocaleDateString()}</span></div><div>{reference.can_open && <a className="secondary-button" href={client.openUrl(workspace, reference.id)} target="_blank" rel="noopener noreferrer">Open in 1Password<ExternalLink size={14} /></a>}{reference.can_manage && <><button className="secondary-button" type="button" onClick={() => startEdit(reference)}>Edit</button><button className="icon-button" type="button" aria-label={`Archive ${reference.title}`} onClick={() => setArchiving(reference)}><Trash2 size={15} /></button></>}</div></li>)}</ul>}
    </section>
    {editing && <section className="content-section credential-reference-form" aria-labelledby="credential-reference-form-heading"><div className="section-heading"><div><h2 id="credential-reference-form-heading">{editing === 'new' ? 'New credential reference' : `Edit ${editing.title}`}</h2><p>Use 1Password’s Copy Private Link. Never paste a password, access token, or public share link.</p></div></div><div className="form-grid"><label><span>Title</span><input value={draft.title} maxLength={240} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label><span>Provider</span><select value="onepassword" disabled><option value="onepassword">1Password</option></select></label><label className="wide-field"><span>{editing === 'new' ? '1Password Private Link' : 'Replacement Private Link (optional)'}</span><input type="url" autoComplete="off" spellCheck={false} value={draft.reference_url} placeholder="https://start.1password.com/open/i?…" onChange={(event) => setDraft({ ...draft, reference_url: event.target.value })} /><small>In 1Password, open the item menu and choose Share, then Copy Private Link.</small></label></div><div className="form-actions"><button className="primary-button" type="button" disabled={saving || !draft.title || (editing === 'new' && !draft.reference_url)} onClick={() => { void save() }}>{saving ? 'Saving…' : 'Save reference'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setEditing(null)}>Cancel</button></div></section>}
    {archiving && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-credential-reference-heading"><div><strong id="archive-credential-reference-heading">Archive {archiving.title}?</strong><p>The pointer will leave this workspace. The 1Password item and its access remain unchanged.</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? 'Archiving…' : 'Archive'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setArchiving(null)}>Cancel</button></div></div>}
  </>
}
