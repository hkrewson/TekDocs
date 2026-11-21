import { useEffect, useId, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { translate } from '../i18n/localization'
import type { RepositoryClient, RepositoryKeyTarget, RepositorySource, RepositorySummary } from './repositoryApi'

export type RepositoryInsertMode = 'document' | 'fragment' | 'record'
export type RepositoryInsertTarget = RepositorySummary | RepositoryKeyTarget

export function RepositoryInsertPicker({ mode, source, organizationId, client, onChoose, onClose }: {
  mode: RepositoryInsertMode
  source: RepositorySource
  organizationId?: string
  client: RepositoryClient
  onChoose: (target: RepositoryInsertTarget, bindings?: Record<string, string>) => void
  onClose: () => void
}) {
  const headingId = useId()
  const dialog = useRef<HTMLElement>(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<RepositoryInsertTarget[]>([])
  const [bindings, setBindings] = useState<Record<string, string>>({})
  const [phase, setPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')

  useEffect(() => {
    const term = query.trim()
    if (!term) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setPhase('loading')
      const request = mode === 'document'
        ? client.list(organizationId, term, controller.signal).then(result => ({ results: result.results.filter(item => item.kind === 'document' && item.id !== source.content_id), bindings: {} }))
        : client.keys(source.content_id, organizationId, term, [], controller.signal).then(result => ({ results: result.targets.filter(item => item.kind === (mode === 'record' ? 'entity' : 'fragment')), bindings: result.key_bindings }))
      void request.then(value => { if (!controller.signal.aborted) { setResults(value.results); setBindings(value.bindings); setPhase('ready') } })
        .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, mode, organizationId, query, source.content_id])

  const title = translate(mode === 'document' ? 'repository.insertDocument' : mode === 'fragment' ? 'repository.insertFragment' : 'repository.insertRecord')
  const handleDialogKey = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') { event.preventDefault(); onClose(); return }
    if (event.key !== 'Tab') return
    const controls = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled])') ?? [])
    if (controls.length === 0) return
    const first = controls[0]
    const last = controls[controls.length - 1]
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }
  return <div className="form-overlay repository-insert-overlay" role="presentation">
    <section ref={dialog} className="record-form repository-insert-picker" role="dialog" aria-modal="true" aria-labelledby={headingId} onKeyDown={handleDialogKey}>
      <div className="section-heading"><h2 id={headingId}>{title}</h2><button className="secondary-button" type="button" onClick={onClose}>{translate('common.close')}</button></div>
      <label>{translate('repository.insertSearch')}<input autoFocus type="search" value={query} onChange={event => { const value = event.target.value; setQuery(value); if (!value.trim()) { setResults([]); setPhase('idle') } }} /></label>
      {phase === 'idle' && <p className="empty-state">{translate('repository.insertSearchHelp')}</p>}
      {phase === 'loading' && <p role="status">{translate('common.loading')}</p>}
      {phase === 'error' && <p role="alert" className="form-message error">{translate('repository.loadFailed')}</p>}
      {phase === 'ready' && results.length === 0 && <p className="empty-state">{translate('repository.insertNoResults')}</p>}
      {results.length > 0 && <ul className="document-title-list">{results.map(target => <li key={target.id}><button type="button" aria-label={translate('repository.insertResult', { title: target.title })} onClick={() => onChoose(target, bindings)}><span><strong>{target.title}</strong><small>{'entity_type' in target ? target.entity_type.replaceAll('_', ' ') : target.kind === 'document' ? translate('repository.document') : translate('repository.fragment')}</small></span></button></li>)}</ul>}
    </section>
  </div>
}
