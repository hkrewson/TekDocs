import { useEffect, useRef, useState } from 'react'
import { CollectionPagination } from '../CollectionPagination'
import { SanitizedMarkdown } from '../editor/SanitizedMarkdown'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { DocumentRecord, DocumentResult, DocumentScope, DocumentsClient, TemplatePlacementMode } from './api'

export function TemplateLibrary({ scope, workspaceName, client, onCreated, urlManaged = false }: { urlManaged?: boolean; scope: DocumentScope; workspaceName: string; client: DocumentsClient; onCreated: (document: DocumentRecord) => void }) {
  const [query, setQuery] = useState(() => urlManaged ? new URLSearchParams(window.location.search).get('template_q') ?? '' : '')
  const [page, setPage] = useState(() => {
    const value = urlManaged ? Number(new URLSearchParams(window.location.search).get('template_page')) : 1
    return Number.isInteger(value) && value > 0 ? value : 1
  })
  useEffect(() => {
    if (!urlManaged) return
    const parameters = new URLSearchParams(window.location.search)
    if (query) parameters.set('template_q', query); else parameters.delete('template_q')
    if (page > 1) parameters.set('template_page', String(page)); else parameters.delete('template_page')
    window.history.replaceState(window.history.state, '', `${window.location.pathname}?${parameters}${window.location.hash}`)
  }, [query, page, urlManaged])
  const [retry, setRetry] = useState(0)
  const [result, setResult] = useState<DocumentResult | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [draft, setDraft] = useState<{ source: DocumentRecord; title: string; rules: Record<string, TemplatePlacementMode> } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const search = useRef<HTMLInputElement>(null)
  const attempt = useUnsavedChanges(Boolean(draft), busy, () => setDraft(null))
  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.listTemplateLibrary(scope, controller.signal, query, page).then((value) => {
        if (!controller.signal.aborted) { setResult(value); if (value.page) setPage(value.page); setPhase('ready') }
      }).catch(() => { if (!controller.signal.aborted) setPhase('error') })
    }, 180)
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [client, scope, query, page, retry])
  const draftId = draft?.source.id
  useEffect(() => { if (draftId) heading.current?.focus(); else search.current?.focus() }, [draftId])
  const cancel = () => attempt(() => { setDraft(null); setError(null) })
  const create = async () => {
    if (!draft || busy || !draft.title.trim()) return
    setBusy(true); setError(null)
    try {
      const document = await client.instantiateTemplate(scope, draft.source.id, draft.title.trim(), draft.source.category, draft.rules)
      setDraft(null); onCreated(document)
    } catch { setError(translate('documentation.templateCreateFailed')) }
    finally { setBusy(false) }
  }
  return <section className="content-section client-template-library" aria-labelledby="client-template-library-heading">
    <h2 id="client-template-library-heading">{translate('documentation.mspTemplates')}</h2>
    {draft ? <section className="template-draft" aria-labelledby="template-draft-heading">
      <div className="section-heading"><h3 ref={heading} tabIndex={-1} id="template-draft-heading">{translate('documentation.createFromTemplate', { title: draft.source.title })}</h3><button className="secondary-button" type="button" disabled={busy} onClick={cancel}>{translate('documentation.cancelTemplate')}</button></div>
      <p>{translate('documentation.templateCopyHelp')}</p>
      {error && <p role="alert">{error}</p>}
      <label>{translate('documentation.clientDocumentTitle')}<input maxLength={240} required disabled={busy} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
      <ul className="template-section-choices">{draft.source.placements.map((placement) => <li key={placement.id}>
        <strong>{placement.block_name.replace(/ — content$/, '')}</strong>
        {placement.is_primary ? <p>{translate('documentation.templatePrimaryCopy')}</p> : <label>{translate('documentation.templateSectionBehavior', { name: placement.block_name.replace(/ — content$/, '') })}<select disabled={busy} value={draft.rules[placement.block_id] ?? 'copy'} onChange={(event) => setDraft({ ...draft, rules: { ...draft.rules, [placement.block_id]: event.target.value as TemplatePlacementMode } })}><option value="copy">{translate('documentation.templateCopyOnce')}</option><option value="live">{translate('documentation.templateKeepUpdated')}</option><option value="pinned">{translate('documentation.templateKeepVersion')}</option></select></label>}
        <details><summary>{translate('documentation.previewSection')}</summary><SanitizedMarkdown html={placement.resolved_html} /></details>
      </li>)}</ul>
      <p>{translate('documentation.templateBehaviorHelp')}</p>
      <div className="document-actions"><button className="primary-button" type="button" disabled={busy || !draft.title.trim()} onClick={() => { void create() }}>{busy ? translate('documentation.creating') : translate('documentation.createDocument')}</button><button className="secondary-button" type="button" disabled={busy} onClick={cancel}>{translate('common.cancel')}</button></div>
    </section> : <>
      <p>{translate('documentation.mspTemplatesHelp')}</p>
      <label>{translate('documentation.searchTemplates')}<input ref={search} type="search" maxLength={120} value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); setPhase('loading') }} /></label>
      {phase === 'loading' && <p role="status">{translate('common.loading')}</p>}
      {phase === 'error' && <div role="alert"><p>{translate('documentation.templateLoadFailed')}</p><button type="button" className="secondary-button" onClick={() => { setPhase('loading'); setRetry((value) => value + 1) }}>{translate('common.retry')}</button></div>}
      {phase === 'ready' && result && <>
        {result.results.length === 0 && <p>{translate('documentation.noTemplates')}</p>}
        <ul>{result.results.map((template) => <li key={template.id}><span><strong>{template.title}</strong><small>{translate('documentation.sectionCount', { count: template.placement_count })}</small></span><button className="secondary-button" type="button" onClick={() => setDraft({ source: template, title: `${workspaceName} — ${template.title}`, rules: Object.fromEntries(template.placements.filter((placement) => !placement.is_primary).map((placement) => [placement.block_id, 'copy'])) })}>{translate('documentation.useTemplate')}</button></li>)}</ul>
        <CollectionPagination label={translate('documentation.templatesLabel')} page={result.page ?? page} pageSize={result.page_size ?? 25} count={result.count} hasMore={result.has_more ?? false} onPageChange={(value) => { setPage(value); setPhase('loading') }} />
      </>}
    </>}
  </section>
}
