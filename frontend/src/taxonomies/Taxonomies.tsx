import { ArrowDown, ArrowUp, Plus, Search, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { CollectionPagination } from '../CollectionPagination'
import { FilterMenu } from '../FilterMenu'
import { translate } from '../i18n/localization'
import type { MessageId } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { TaxonomiesClient, Taxonomy, TaxonomyBinding, TaxonomyInput, TaxonomyTerm } from './api'

const bindingOptions: { value: TaxonomyBinding; labelKey: MessageId }[] = [
  { value: 'document_tags', labelKey: 'taxonomies.binding.documentTags' }, { value: 'technology', labelKey: 'taxonomies.binding.technology' },
  { value: 'service_family', labelKey: 'taxonomies.binding.serviceFamily' }, { value: 'platform', labelKey: 'taxonomies.binding.platform' },
  { value: 'risk_level', labelKey: 'taxonomies.binding.riskLevel' }, { value: 'support_tier', labelKey: 'taxonomies.binding.supportTier' },
  { value: 'compliance_domain', labelKey: 'taxonomies.binding.complianceDomain' }, { value: 'document_subject', labelKey: 'taxonomies.binding.documentSubject' },
]
const pageSizes = [25, 50, 100] as const
type TermDraft = Omit<TaxonomyTerm, 'id' | 'impact'>
type Draft = Omit<TaxonomyInput, 'terms'> & { terms: TermDraft[] }
const emptyTerm = (): TermDraft => ({ stable_key: '', label: '', description: '', parent_key: '', aliases: [], status: 'active', replacement_key: '', sort_order: 0 })
const emptyDraft = (): Draft => ({ key: '', binding: 'document_tags', label: '', description: '', allow_local_terms: false, terms: [emptyTerm()] })
function pageFrom(value: string | null) { const parsed = Number(value); return Number.isInteger(parsed) && parsed > 0 ? parsed : 1 }
function pageSizeFrom(value: string | null): typeof pageSizes[number] { const parsed = Number(value); return pageSizes.includes(parsed as typeof pageSizes[number]) ? parsed as typeof pageSizes[number] : 25 }
function bindingFrom(value: string | null): TaxonomyBinding | '' { return bindingOptions.some((option) => option.value === value) ? value as TaxonomyBinding : '' }
function bindingLabel(value: TaxonomyBinding) { return translate(bindingOptions.find((option) => option.value === value)?.labelKey ?? 'taxonomies.binding.documentTags') }
function draftFor(taxonomy?: Taxonomy): Draft {
  if (!taxonomy) return emptyDraft()
  return { key: taxonomy.key, binding: taxonomy.binding, label: taxonomy.current_version.label, description: taxonomy.current_version.description, allow_local_terms: taxonomy.current_version.allow_local_terms, terms: taxonomy.current_version.terms.map(({ stable_key, label, description, parent_key, aliases, status, replacement_key, sort_order }) => ({ stable_key, label, description, parent_key, aliases, status, replacement_key, sort_order })) }
}

function TaxonomyEditor({ taxonomy, saving, closingAfterSave, error, onCancel, onSave }: { taxonomy?: Taxonomy; saving: boolean; closingAfterSave: boolean; error: string | null; onCancel: () => void; onSave: (draft: Draft) => Promise<void> }) {
  const initial = useMemo(() => draftFor(taxonomy), [taxonomy])
  const [draft, setDraft] = useState(initial)
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial)
  const attempt = useUnsavedChanges(dirty && !closingAfterSave, saving && !closingAfterSave, undefined, !closingAfterSave)
  useEffect(() => {
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = overflow }
  }, [])
  const updateTerm = (index: number, patch: Partial<TermDraft>) => setDraft((current) => ({ ...current, terms: current.terms.map((term, position) => position === index ? { ...term, ...patch } : term) }))
  const moveTerm = (index: number, offset: -1 | 1) => setDraft((current) => {
    const target = index + offset
    if (target < 0 || target >= current.terms.length) return current
    const terms = [...current.terms]
    ;[terms[index], terms[target]] = [terms[target], terms[index]]
    return { ...current, terms }
  })
  const valid = draft.key && draft.label && draft.terms.every((term) => term.stable_key && term.label)

  return <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="taxonomy-editor-heading"><form className="record-form taxonomy-editor" onSubmit={(event) => { event.preventDefault(); void onSave({ ...draft, terms: draft.terms.map((term, index) => ({ ...term, sort_order: index })) }) }}>
    <div className="section-heading"><div><h2 id="taxonomy-editor-heading">{taxonomy ? translate('taxonomies.newVersionFor', { name: taxonomy.current_version.label }) : translate('taxonomies.new')}</h2><p>{translate('taxonomies.editorHelp')}</p></div></div>
    {error && <div className="form-message error" role="alert">{error}</div>}
    <div className="document-detail-fields">
      <label>{translate('taxonomies.key')}<input autoFocus value={draft.key} disabled={Boolean(taxonomy)} onChange={(event) => setDraft({ ...draft, key: event.target.value })} /></label>
      <label>{translate('taxonomies.binding')}<select value={draft.binding} disabled={Boolean(taxonomy)} onChange={(event) => setDraft({ ...draft, binding: event.target.value as TaxonomyBinding })}>{bindingOptions.map((option) => <option key={option.value} value={option.value}>{translate(option.labelKey)}</option>)}</select></label>
      <label>{translate('taxonomies.label')}<input value={draft.label} maxLength={120} onChange={(event) => setDraft({ ...draft, label: event.target.value })} /></label>
      <label>{translate('taxonomies.description')}<input value={draft.description} maxLength={500} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
    </div>
    <label className="checkbox-label"><input type="checkbox" checked={draft.allow_local_terms} onChange={(event) => setDraft({ ...draft, allow_local_terms: event.target.checked })} />{translate('taxonomies.allowLocal')}</label>
    <div className="section-heading"><h3>{translate('taxonomies.terms')}</h3><button className="secondary-button" type="button" onClick={() => setDraft({ ...draft, terms: [...draft.terms, emptyTerm()] })}><Plus size={15} />{translate('taxonomies.addTerm')}</button></div>
    <div className="taxonomy-term-list">{draft.terms.map((term, index) => <fieldset key={`${term.stable_key}-${index}`} className="taxonomy-term-row"><legend>{term.label || translate('taxonomies.termNumber', { number: index + 1 })}{taxonomy && term.stable_key && <small>{translate('taxonomies.termUsage', taxonomy.current_version.terms.find((existing) => existing.stable_key === term.stable_key)?.impact ?? { documents: 0, templates: 0 })}</small>}</legend><div className="document-detail-fields">
      <label>{translate('taxonomies.termKey')}<input value={term.stable_key} maxLength={80} onChange={(event) => updateTerm(index, { stable_key: event.target.value })} /></label>
      <label>{translate('taxonomies.termLabel')}<input value={term.label} maxLength={120} onChange={(event) => updateTerm(index, { label: event.target.value })} /></label>
      <label>{translate('taxonomies.parent')}<select value={term.parent_key} onChange={(event) => updateTerm(index, { parent_key: event.target.value })}><option value="">{translate('taxonomies.noParent')}</option>{draft.terms.filter((candidate, position) => position !== index && candidate.stable_key).map((candidate) => <option key={candidate.stable_key} value={candidate.stable_key}>{candidate.label || candidate.stable_key}</option>)}</select></label>
      <label>{translate('taxonomies.aliases')}<input value={term.aliases.join(', ')} maxLength={400} onChange={(event) => updateTerm(index, { aliases: event.target.value.split(',').map((value) => value.trim()).filter(Boolean) })} /></label>
      <label>{translate('taxonomies.status')}<select value={term.status} onChange={(event) => updateTerm(index, { status: event.target.value as TermDraft['status'] })}><option value="active">{translate('taxonomies.active')}</option><option value="retired">{translate('taxonomies.retired')}</option></select></label>
      <label>{translate('taxonomies.replacement')}<select value={term.replacement_key} disabled={term.status !== 'retired'} onChange={(event) => updateTerm(index, { replacement_key: event.target.value })}><option value="">{translate('taxonomies.noReplacement')}</option>{draft.terms.filter((candidate, position) => position !== index && candidate.stable_key && candidate.status === 'active').map((candidate) => <option key={candidate.stable_key} value={candidate.stable_key}>{candidate.label || candidate.stable_key}</option>)}</select></label>
    </div><label>{translate('taxonomies.termDescription')}<input value={term.description} maxLength={500} onChange={(event) => updateTerm(index, { description: event.target.value })} /></label><div className="row-actions"><button className="row-action" type="button" disabled={index === 0} onClick={() => moveTerm(index, -1)}><ArrowUp size={14} />{translate('taxonomies.moveUp')}</button><button className="row-action" type="button" disabled={index === draft.terms.length - 1} onClick={() => moveTerm(index, 1)}><ArrowDown size={14} />{translate('taxonomies.moveDown')}</button><button className="row-action danger" type="button" disabled={draft.terms.length === 1} onClick={() => setDraft({ ...draft, terms: draft.terms.filter((_, position) => position !== index) })}><Trash2 size={14} />{translate('common.remove')}</button></div></fieldset>)}</div>
    <div className="form-actions"><button className="primary-button" disabled={saving || !valid}>{saving ? translate('common.saving') : translate('taxonomies.save')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => attempt(onCancel)}>{translate('common.cancel')}</button></div>
  </form></section>
}

export function Taxonomies({ client }: { client: TaxonomiesClient }) {
  const [parameters, setParameters] = useSearchParams()
  const query = parameters.get('q') ?? ''
  const binding = bindingFrom(parameters.get('binding'))
  const page = pageFrom(parameters.get('page'))
  const pageSize = pageSizeFrom(parameters.get('page_size'))
  const editorId = parameters.get('taxonomy')
  const migrationOpen = parameters.get('view') === 'migration'
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [items, setItems] = useState<Taxonomy[]>([])
  const [saving, setSaving] = useState(false)
  const [closingAfterSave, setClosingAfterSave] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pendingArchive, setPendingArchive] = useState<Taxonomy | null>(null)
  const [migration, setMigration] = useState<Awaited<ReturnType<TaxonomiesClient['migration']>> | null>(null)
  const [revision, setRevision] = useState(0)

  function updateParameters(changes: Record<string, string | number | null>, replace = false) {
    const next = new URLSearchParams(parameters)
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === '' || key === 'page' && value === 1 || key === 'page_size' && value === 25) next.delete(key)
      else next.set(key, String(value))
    }
    setParameters(next, { replace })
  }
  const load = useCallback((signal?: AbortSignal) => {
    setPhase('loading'); setError(null)
    void client.list(undefined, signal).then((result) => { if (!signal?.aborted) { setItems(result.results); setPhase('ready') } }).catch(() => { if (!signal?.aborted) { setError(translate('taxonomies.loadFailed')); setPhase('error') } })
  }, [client])
  useEffect(() => {
    const controller = new AbortController()
    void client.list(undefined, controller.signal).then((result) => { if (!controller.signal.aborted) { setItems(result.results); setPhase('ready') } }).catch(() => { if (!controller.signal.aborted) { setError(translate('taxonomies.loadFailed')); setPhase('error') } })
    return () => controller.abort()
  }, [client, revision])
  const selected = editorId === 'new' ? undefined : items.find((item) => item.id === editorId)
  const filtered = items.filter((taxonomy) => (!query || `${taxonomy.current_version.label} ${taxonomy.key} ${taxonomy.current_version.description}`.toLowerCase().includes(query.toLowerCase())) && (!binding || taxonomy.binding === binding))
  const first = (page - 1) * pageSize
  const visible = filtered.slice(first, first + pageSize)

  const save = async (draft: Draft) => {
    setSaving(true); setError(null)
    try {
      if (selected) await client.revise(selected.id, { label: draft.label, description: draft.description, allow_local_terms: draft.allow_local_terms, terms: draft.terms })
      else await client.create(draft)
      setClosingAfterSave(true)
      window.setTimeout(() => { updateParameters({ taxonomy: null }); setClosingAfterSave(false) }, 50)
      load()
    } catch { setError(translate('taxonomies.saveFailed')) } finally { setSaving(false) }
  }
  const previewMigration = async (apply: boolean) => {
    setSaving(true); setError(null)
    try { setMigration(await client.migration(apply)) } catch { setError(translate('taxonomies.migrationFailed')) } finally { setSaving(false) }
  }
  const archive = async () => {
    if (!pendingArchive) return
    setSaving(true); setError(null)
    try { await client.archive(pendingArchive.id); setPendingArchive(null); load() }
    catch { setError(translate('taxonomies.archiveFailed')) } finally { setSaving(false) }
  }

  return <>
    <header className="page-header"><div><h1>{translate('taxonomies.heading')}</h1><p>{translate('taxonomies.intro')}</p></div><div className="page-actions"><button className="secondary-button" type="button" aria-pressed={migrationOpen} onClick={() => updateParameters({ view: migrationOpen ? null : 'migration' })}>{migrationOpen ? translate('taxonomies.backToDefinitions') : translate('taxonomies.migration')}</button><button className="primary-button" type="button" onClick={() => { setClosingAfterSave(false); updateParameters({ taxonomy: 'new' }) }}><Plus size={17} />{translate('taxonomies.new')}</button></div></header>
    {editorId && (editorId === 'new' || selected) && <TaxonomyEditor key={editorId} taxonomy={selected} saving={saving} closingAfterSave={closingAfterSave} error={error} onCancel={() => updateParameters({ taxonomy: null })} onSave={save} />}
    {editorId && editorId !== 'new' && phase === 'ready' && !selected && <div className="form-message warning" role="alert">{translate('taxonomies.taxonomyUnavailable')} <button className="row-action" type="button" onClick={() => updateParameters({ taxonomy: null })}>{translate('common.close')}</button></div>}
    {error && !editorId && phase !== 'error' && <div className="form-message error" role="alert">{error}</div>}
    {migrationOpen ? <section className="content-section" aria-labelledby="taxonomy-migration-heading"><div className="section-heading"><div><h2 id="taxonomy-migration-heading">{translate('taxonomies.migration')}</h2><p>{translate('taxonomies.migrationIntro')}</p></div><button className="secondary-button" type="button" disabled={saving} onClick={() => { void previewMigration(false) }}>{translate('taxonomies.preview')}</button></div>{migration && <><p role="status">{translate('taxonomies.migrationSummary', migration.counts)}</p>{migration.rows.length > 0 && <ol className="plain-detail-list metadata-list">{migration.rows.map((row, index) => <li key={`${row.document_id}-${row.tag}-${index}`}><div><strong>{row.document_title}</strong><span>{translate('taxonomies.legacyTag')}: {row.tag}</span></div><span>{row.term_label ?? row.status}</span></li>)}</ol>}{migration.counts.matched > 0 && <button className="primary-button" type="button" disabled={saving} onClick={() => { void previewMigration(true) }}>{translate('taxonomies.applyMigration')}</button>}</>}</section>
      : <section className="content-section" aria-busy={phase === 'loading'}>
        <div className="section-heading"><h2>{translate('taxonomies.definitions')}</h2><span>{translate('taxonomies.count', { count: filtered.length })}</span></div>
        <div className="collection-toolbar metadata-toolbar"><label className="collection-search"><Search size={16} aria-hidden="true" /><span className="sr-only">{translate('taxonomies.search')}</span><input type="search" value={query} placeholder={translate('taxonomies.search')} onChange={(event) => updateParameters({ q: event.target.value, page: 1 }, true)} /></label><FilterMenu groups={[{ kind: 'choices', label: translate('taxonomies.binding'), value: binding, choices: [{ value: '', label: translate('taxonomies.allBindings') }, ...bindingOptions.map((option) => ({ value: option.value, label: translate(option.labelKey) }))], onChange: (value) => updateParameters({ binding: value, page: 1 }) }]} activeCount={binding ? 1 : 0} onClear={() => updateParameters({ binding: null, page: 1 })} /><label className="collection-page-size">{translate('collections.pageSize')}<select value={pageSize} onChange={(event) => updateParameters({ page_size: Number(event.target.value), page: 1 })}>{pageSizes.map((size) => <option key={size} value={size}>{size}</option>)}</select></label></div>
        {(query || binding) && <div className="collection-active-filters">{query && <button className="row-action" type="button" onClick={() => updateParameters({ q: null, page: 1 })}>{translate('taxonomies.searchSummary', { query })} ×</button>}{binding && <button className="row-action" type="button" onClick={() => updateParameters({ binding: null, page: 1 })}>{bindingLabel(binding)} ×</button>}</div>}
        {phase === 'loading' && <p className="empty-state" role="status">{translate('taxonomies.loading')}</p>}
        {phase === 'error' && <div className="empty-state" role="alert"><p>{error ?? translate('taxonomies.loadFailed')}</p><button className="secondary-button" type="button" onClick={() => { setPhase('loading'); setError(null); setRevision((value) => value + 1) }}>{translate('common.retry')}</button></div>}
        {phase === 'ready' && filtered.length === 0 && <p className="empty-state">{query || binding ? translate('taxonomies.noMatches') : translate('taxonomies.empty')}</p>}
        {phase === 'ready' && visible.length > 0 && <ol className="plain-detail-list metadata-list">{visible.map((taxonomy) => <li key={taxonomy.id}><div><strong>{taxonomy.current_version.label}</strong><span><code>{taxonomy.key}</code> · {bindingLabel(taxonomy.binding)}</span><span>{translate('taxonomies.versionSummary', { version: taxonomy.current_version.version, count: taxonomy.current_version.terms.length })} · {translate('taxonomies.usageCount', taxonomy.impact)}</span>{taxonomy.current_version.description && <span>{taxonomy.current_version.description}</span>}</div><div className="row-actions"><button className="row-action" type="button" onClick={() => { setClosingAfterSave(false); updateParameters({ taxonomy: taxonomy.id }) }}>{translate('taxonomies.newVersion')}</button><button className="row-action danger" type="button" onClick={() => setPendingArchive(taxonomy)}>{translate('common.archive')}</button></div></li>)}</ol>}
        <CollectionPagination label={translate('taxonomies.definitions')} page={page} pageSize={pageSize} count={filtered.length} hasMore={first + pageSize < filtered.length} onPageChange={(nextPage) => updateParameters({ page: nextPage })} />
        {pendingArchive && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-taxonomy-heading"><div><strong id="archive-taxonomy-heading">{translate('taxonomies.archiveHeading', { name: pendingArchive.current_version.label })}</strong><p>{translate('taxonomies.archiveConfirm')}</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? translate('common.saving') : translate('common.archive')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setPendingArchive(null)}>{translate('common.cancel')}</button></div></div>}
      </section>}
  </>
}
