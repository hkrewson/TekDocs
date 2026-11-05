import { useEffect, useId, useState } from 'react'
import { flushSync } from 'react-dom'
import { CollectionPagination } from '../CollectionPagination'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import { browserRepositoryClient, RepositoryConflictError, type RepositoryClient, type RepositorySource, type RepositoryTemplateAction, type RepositoryTemplateDefinition, type RepositoryTemplateMode, type RepositoryTemplatePage, type RepositoryTemplateState } from './repositoryApi'

type Rule = RepositoryTemplateMode | 'keep'
function Behavior({ title, value, onChange, keep = false, disabled = false }: { title: string; value: Rule; onChange: (value: Rule) => void; keep?: boolean; disabled?: boolean }) {
  const id = useId()
  return <><label htmlFor={id}>{translate('repository.templates.behavior', { title })}</label><select id={id} value={value} disabled={disabled} onChange={event => onChange(event.target.value as Rule)}>
    {keep && <option value="keep">{translate('repository.templates.keep')}</option>}
    <option value="copy">{translate('documentation.templateCopyOnce')}</option><option value="live">{translate('documentation.templateKeepUpdated')}</option><option value="pinned">{translate('documentation.templateKeepVersion')}</option>
  </select></>
}
function failure(error: unknown) {
  if (error instanceof RepositoryConflictError) {
    const detail: unknown = error.conflict && 'detail' in error.conflict ? error.conflict.detail : undefined
    return typeof detail === 'string' && detail.length < 300 ? detail : translate('repository.templates.stale')
  }
  return error instanceof Error ? error.message : translate('repository.templates.failed')
}

export function RepositoryTemplates({ source, organizationId, client, disabled, onSaved, onEditingChange }: { source: RepositorySource; organizationId?: string; client: RepositoryClient; disabled: boolean; onSaved: (source: RepositorySource) => void; onEditingChange: (editing: boolean) => void }) {
  const [opened, setOpened] = useState(false), [state, setState] = useState<RepositoryTemplateState | null>(null)
  const [config, setConfig] = useState<RepositoryTemplateState['source']>(), [rules, setRules] = useState<Record<string, Rule>>({})
  const [loading, setLoading] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(''), [retry, setRetry] = useState(0)
  const dirty = !!state && (JSON.stringify(config) !== JSON.stringify(state.source) || Object.keys(rules).length > 0)
  const close = () => { setOpened(false); setState(null); setConfig(undefined); setRules({}); setError('') }
  const attempt = useUnsavedChanges(dirty, busy, close, opened)
  useEffect(() => { onEditingChange(opened); return () => onEditingChange(false) }, [opened, onEditingChange])
  useEffect(() => {
    if (!opened) return
    const controller = new AbortController()
    client.template(source.content_id, organizationId, controller.signal).then(value => {
      if (!controller.signal.aborted) { setState(value); setConfig(value.source); setRules({}); setLoading(false) }
    }).catch(error => { if (!controller.signal.aborted) { setError(failure(error)); setLoading(false) } })
    return () => controller.abort()
  }, [opened, client, source.content_id, source.source_blob, organizationId, retry])
  async function write(action: RepositoryTemplateAction) {
    if (busy || disabled || !state || state.read_only) return
    setBusy(true); setError('')
    try {
      const updated = await client.templateAction(source.content_id, action, organizationId)
      flushSync(() => { close(); setBusy(false) })
      onSaved(updated)
    } catch (error) { setError(failure(error)) } finally { setBusy(false) }
  }
  const enrollment = state?.enrollment
  const review = enrollment && { base_commit: enrollment.expected_base, base_blob: enrollment.expected_blob, expected_applied_revision_id: enrollment.applied_revision_id, expected_available_revision_id: enrollment.available_revision_id }
  const locked = disabled || busy || !!state?.read_only
  const unresolved = enrollment?.changes.some(row => ['conflict', 'removed'].includes(row.state) && !rules[row.id])
  return <section className="content-section" aria-label={translate('repository.templates.heading')}>
    <button type="button" className="secondary-button" disabled={disabled || busy} aria-expanded={opened} onClick={() => opened ? attempt(close) : (setLoading(true), setOpened(true))}>{translate('repository.templates.heading')}</button>
    {disabled && <p>{translate('repository.templates.disabled')}</p>}
    {opened && <>
      {loading && <p role="status">{translate('common.loading')}</p>}
      {error && <div role="alert"><p>{error}</p>{!state && <button type="button" onClick={() => { setError(''); setLoading(true); setRetry(value => value + 1) }}>{translate('common.retry')}</button>}</div>}
      {state?.read_only && <p>{translate('repository.templates.readOnly')}</p>}
      {state?.role === 'source' && config && <fieldset disabled={locked}>
        <legend>{translate('repository.templates.sections')}</legend>
        <label><input type="checkbox" checked={config.enabled} onChange={event => setConfig({ ...config, enabled: event.target.checked })} />{translate('repository.templates.enabled')}</label>
        <label><input type="checkbox" checked={config.library_visible} onChange={event => setConfig({ ...config, library_visible: event.target.checked })} />{translate('repository.templates.visible')}</label>
        {config.fragments.map(fragment => <div key={fragment.id}><label><input type="checkbox" checked={config.selected_fragment_ids.includes(fragment.id)} onChange={event => setConfig({ ...config, selected_fragment_ids: event.target.checked ? [...config.selected_fragment_ids, fragment.id] : config.selected_fragment_ids.filter(id => id !== fragment.id) })} />{fragment.title}</label><details><summary>{translate('documentation.previewSection')}</summary><pre>{fragment.markdown}</pre></details></div>)}
        <button type="button" className="primary-button" disabled={!dirty} onClick={() => { void write({ action: 'configure', base_commit: source.accepted_commit, base_blob: source.source_blob, enabled: config.enabled, library_visible: config.library_visible, fragment_ids: config.selected_fragment_ids }) }}>{translate('repository.templates.save')}</button>
      </fieldset>}
      {enrollment && review && <>
        <h3>{translate('repository.templates.source', { title: enrollment.source_title })}</h3><p>{translate('repository.templates.review')}</p>
        <ul>{enrollment.changes.map(row => <li key={row.id}><strong>{row.title}</strong><p>{translate(`repository.templates.${row.state}`)}</p>{row.state === 'conflict' && <p>{translate('repository.templates.conflictHelp')}</p>}{row.mode === 'copy' && row.current_markdown !== undefined && <><h4>{translate('repository.templates.local')}</h4><pre>{row.current_markdown}</pre></>}<h4>{translate('repository.templates.proposed')}</h4><pre>{row.markdown}</pre>
          {row.state === 'removed' ? <label><input type="checkbox" disabled={locked} checked={rules[row.id] === 'keep'} onChange={event => setRules(current => { const next = { ...current }; if (event.target.checked) next[row.id] = 'keep'; else delete next[row.id]; return next })} />{translate('repository.templates.keep')}</label>
            : <Behavior title={row.title} disabled={locked} keep={row.state !== 'added'} value={rules[row.id] ?? (row.state === 'added' ? 'copy' : 'keep')} onChange={value => setRules({ ...rules, [row.id]: value })} />}
          {row.state === 'conflict' && !rules[row.id] && <button type="button" disabled={locked} onClick={() => setRules({ ...rules, [row.id]: 'keep' })}>{translate('repository.templates.keep')}</button>}
          {row.mode !== 'copy' && row.state !== 'removed' && <button className="secondary-button" type="button" disabled={locked || dirty} onClick={() => { void write({ action: 'detach', section_id: row.id, ...review }) }}>{translate('repository.templates.detach', { title: row.title })}</button>}
        </li>)}</ul>
        <button type="button" className="primary-button" disabled={locked || unresolved || (!enrollment.can_apply && !dirty)} onClick={() => { void write({ action: 'apply', ...review, rules: Object.fromEntries(enrollment.changes.map(row => [row.id, rules[row.id] ?? (row.state === 'added' ? 'copy' : 'keep')])) }) }}>{translate('repository.templates.apply')}</button>
      </>}
      <button type="button" className="secondary-button" disabled={busy} onClick={() => attempt(close)}>{translate('common.close')}</button>
    </>}
  </section>
}

export function RepositoryTemplateLibrary({ organizationId, workspaceName, client = browserRepositoryClient, onCreated }: { organizationId: string; workspaceName: string; client?: RepositoryClient; onCreated: (source: RepositorySource) => void }) {
  const [page, setPage] = useState(1), [query, setQuery] = useState(''), [retry, setRetry] = useState(0)
  const [result, setResult] = useState<RepositoryTemplatePage | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState<{ source: RepositoryTemplateDefinition; title: string; rules: Record<string, RepositoryTemplateMode> } | null>(null)
  const attempt = useUnsavedChanges(!!draft, busy, () => setDraft(null))
  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.templates(organizationId, query, page, controller.signal).then(value => { if (!controller.signal.aborted) setResult(value) }).catch(error => { if (!controller.signal.aborted) setError(failure(error)) })
    }, 180)
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [client, organizationId, query, page, retry])
  async function create() {
    if (!draft || busy || !draft.title.trim()) return
    setBusy(true); setError('')
    try {
      const created = await client.enrollTemplate(organizationId, { source_content_id: draft.source.id, definition_sha256: draft.source.definition_sha256, title: draft.title.trim(), rules: draft.rules })
      flushSync(() => { setDraft(null); setBusy(false) })
      onCreated(created)
    } catch (error) { setError(failure(error)) } finally { setBusy(false) }
  }
  return <section className="content-section repository-template-library" aria-label={translate('repository.templates.library')}><h3>{translate('repository.templates.library')}</h3>
    {error && <div role="alert"><p>{error}</p>{!draft && <button type="button" onClick={() => { setError(''); setResult(null); setRetry(value => value + 1) }}>{translate('common.retry')}</button>}</div>}
    {draft ? <>
      <p>{translate('documentation.templatePrimaryCopy')}</p>
      <label>{translate('documentation.clientDocumentTitle')}<input value={draft.title} maxLength={240} disabled={busy} onChange={event => setDraft({ ...draft, title: event.target.value })} /></label>
      {draft.source.sections.map(section => <div key={section.id}><h4>{section.title}</h4><Behavior title={section.title} value={draft.rules[section.id]} disabled={busy} onChange={value => setDraft({ ...draft, rules: { ...draft.rules, [section.id]: value as RepositoryTemplateMode } })} /><details><summary>{translate('documentation.previewSection')}</summary><pre>{section.markdown}</pre></details></div>)}
      <p>{translate('documentation.templateBehaviorHelp')}</p>
      <button type="button" className="primary-button" disabled={busy || !draft.title.trim()} onClick={() => { void create() }}>{translate('repository.templates.create')}</button>
      <button type="button" className="secondary-button" disabled={busy} onClick={() => attempt(() => { setDraft(null); setError(''); setResult(null); setRetry(value => value + 1) })}>{translate('common.cancel')}</button>
    </> : <>
      <label>{translate('repository.templates.search')}<input type="search" maxLength={120} value={query} onChange={event => { setQuery(event.target.value); setPage(1); setResult(null); setError('') }} /></label>
      {!result && !error && <p role="status">{translate('common.loading')}</p>}
      {result?.results.length === 0 && <p>{translate('repository.templates.empty')}</p>}
      <ul>{result?.results.map(template => <li key={template.id}><strong>{template.title}</strong><button type="button" className="secondary-button" onClick={() => attempt(() => { setError(''); setDraft({ source: template, title: `${workspaceName} — ${template.title}`, rules: Object.fromEntries(template.sections.map(section => [section.id, 'copy'])) }) })}>{translate('repository.templates.use')}</button></li>)}</ul>
      {result && result.count > result.page_size && <CollectionPagination label={translate('repository.templates.library')} page={result.page} pageSize={result.page_size} count={result.count} hasMore={result.has_more} onPageChange={value => { setPage(value); setResult(null) }} />}
    </>}
  </section>
}
