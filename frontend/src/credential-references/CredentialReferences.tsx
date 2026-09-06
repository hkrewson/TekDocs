import { useEffect, useState } from 'react'
import { ExternalLink, KeyRound, Plus, Search, Trash2 } from 'lucide-react'
import { translate } from '../i18n/localization'

import type { WorkspaceContext } from '../workspaces/api'
import { CollectionPagination } from '../CollectionPagination'
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
  const [page, setPage] = useState(1)
  const [pageState, setPageState] = useState({ pageSize: 50, count: 0, hasMore: false })

  useEffect(() => {
    const controller = new AbortController()
    client.list(workspace, query, page, controller.signal)
      .then((result) => { setReferences(result.results); setCanManage(result.can_manage); setPageState({ pageSize: result.page_size, count: result.count, hasMore: result.has_more }); setPhase('ready') })
      .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client, page, query, workspace])

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
      setError(caught instanceof Error ? caught.message : translate('credentials.saveFailed'))
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
      setError(caught instanceof Error ? caught.message : translate('credentials.archiveFailed'))
    } finally {
      setSaving(false)
    }
  }

  return <>
    <header className="page-header"><div><h1>{translate('credentials.heading')}</h1><p>{translate('credentials.intro')}</p></div>{canManage && <button className="primary-button" type="button" aria-label={translate('credentials.new')} title={translate('credentials.new')} onClick={() => startEdit('new')}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('credentials.new')}</span></button>}</header>
    {error && <div className="form-message error" role="alert">{error}</div>}
    <section className="content-section credential-reference-section" aria-busy={phase === 'loading'}>
      <div className="credential-reference-boundary"><KeyRound size={18} aria-hidden="true" /><div><strong>{translate('credentials.staysInOnePassword')}</strong><p>{translate('credentials.boundaryHelp')}</p></div></div>
      <label className="credential-reference-search"><span>{translate('credentials.search')}</span><div><Search size={16} /><input value={query} onChange={(event) => { setPhase('loading'); setQuery(event.target.value); setPage(1) }} placeholder={translate('credentials.searchPlaceholder')} /></div></label>
      {phase === 'loading' && <p className="empty-state" role="status">{translate('credentials.loading')}</p>}
      {phase === 'error' && <p className="empty-state" role="alert">{translate('credentials.unavailable')}</p>}
      {phase === 'ready' && references.length === 0 && <p className="empty-state">{query ? translate('credentials.noMatches') : translate('credentials.empty')}</p>}
      {phase === 'ready' && references.length > 0 && <><ul className="credential-reference-list">{references.map((reference) => <li key={reference.id}><div><strong>{reference.title}</strong><span>{reference.provider_label} · {translate('credentials.updated', { date: new Date(reference.updated_at).toLocaleDateString() })}</span></div><div>{reference.can_open && <a className="secondary-button" href={client.openUrl(workspace, reference.id)} target="_blank" rel="noopener noreferrer">{translate('credentials.open')}<ExternalLink size={14} /></a>}{reference.can_manage && <><button className="secondary-button" type="button" onClick={() => startEdit(reference)}>{translate('common.edit')}</button><button className="icon-button" type="button" title={translate('credentials.archive', { title: reference.title })} aria-label={translate('credentials.archive', { title: reference.title })} onClick={() => setArchiving(reference)}><Trash2 size={15} /></button></>}</div></li>)}</ul><CollectionPagination label={translate('credentials.heading')} page={page} pageSize={pageState.pageSize} count={pageState.count} hasMore={pageState.hasMore} onPageChange={(next) => { setPhase('loading'); setPage(next) }} /></>}
    </section>
    {editing && <section className="content-section credential-reference-form" aria-labelledby="credential-reference-form-heading"><div className="section-heading"><div><h2 id="credential-reference-form-heading">{editing === 'new' ? translate('credentials.newHeading') : translate('credentials.editHeading', { title: editing.title })}</h2><p>{translate('credentials.formHelp')}</p></div></div><div className="form-grid"><label><span>{translate('credentials.title')}</span><input value={draft.title} maxLength={240} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label className="wide-field"><span>{editing === 'new' ? translate('credentials.privateLink') : translate('credentials.replacementLink')}</span><input type="url" autoComplete="off" spellCheck={false} value={draft.reference_url} placeholder="https://start.1password.com/open/i?…" onChange={(event) => setDraft({ ...draft, reference_url: event.target.value })} /><small>{translate('credentials.copyHelp')}</small></label></div><div className="form-actions"><button className="primary-button" type="button" disabled={saving || !draft.title || (editing === 'new' && !draft.reference_url)} onClick={() => { void save() }}>{saving ? translate('common.saving') : translate('credentials.save')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setEditing(null)}>{translate('common.cancel')}</button></div></section>}
    {archiving && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-credential-reference-heading"><div><strong id="archive-credential-reference-heading">{translate('credentials.archiveHeading', { title: archiving.title })}</strong><p>{translate('credentials.archiveHelp')}</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? translate('credentials.archiving') : translate('common.archive')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setArchiving(null)}>{translate('common.cancel')}</button></div></div>}
  </>
}
