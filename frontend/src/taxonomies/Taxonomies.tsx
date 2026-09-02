import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { translate } from '../i18n/localization'
import type { TaxonomiesClient, Taxonomy, TaxonomyBinding, TaxonomyInput, TaxonomyTerm } from './api'

const bindingOptions: { value: TaxonomyBinding; label: string }[] = [
  { value: 'document_tags', label: 'Document tags' },
  { value: 'technology', label: 'Technology' },
  { value: 'service_family', label: 'Service family' },
  { value: 'platform', label: 'Platform' },
  { value: 'risk_level', label: 'Risk level' },
  { value: 'support_tier', label: 'Support tier' },
  { value: 'compliance_domain', label: 'Compliance domain' },
  { value: 'document_subject', label: 'Document subject' },
]

type TermDraft = Omit<TaxonomyTerm, 'id' | 'impact'>
type Draft = Omit<TaxonomyInput, 'terms'> & { terms: TermDraft[] }
const emptyTerm = (): TermDraft => ({ stable_key: '', label: '', description: '', parent_key: '', aliases: [], status: 'active', replacement_key: '', sort_order: 0 })
const emptyDraft = (): Draft => ({ key: '', binding: 'document_tags', label: '', description: '', allow_local_terms: false, terms: [emptyTerm()] })

export function Taxonomies({ client }: { client: TaxonomiesClient }) {
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [items, setItems] = useState<Taxonomy[]>([])
  const [editing, setEditing] = useState<Taxonomy | 'new' | null>(null)
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [migration, setMigration] = useState<Awaited<ReturnType<TaxonomiesClient['migration']>> | null>(null)

  const load = useCallback(() => {
    const controller = new AbortController()
    client.list(undefined, controller.signal).then((result) => { setItems(result.results); setPhase('ready') }).catch((cause: unknown) => { if (!controller.signal.aborted) { setError(cause instanceof Error ? cause.message : translate('taxonomies.loadFailed')); setPhase('error') } })
    return () => controller.abort()
  }, [client])
  useEffect(() => load(), [load])

  const start = (taxonomy?: Taxonomy) => {
    setError(null)
    if (!taxonomy) { setEditing('new'); setDraft(emptyDraft()); return }
    setEditing(taxonomy)
    setDraft({
      key: taxonomy.key,
      binding: taxonomy.binding,
      label: taxonomy.current_version.label,
      description: taxonomy.current_version.description,
      allow_local_terms: taxonomy.current_version.allow_local_terms,
      terms: taxonomy.current_version.terms.map((term) => ({
        stable_key: term.stable_key,
        label: term.label,
        description: term.description,
        parent_key: term.parent_key,
        aliases: term.aliases,
        status: term.status,
        replacement_key: term.replacement_key,
        sort_order: term.sort_order,
      })),
    })
  }
  const updateTerm = (index: number, patch: Partial<TermDraft>) => setDraft((current) => ({ ...current, terms: current.terms.map((term, position) => position === index ? { ...term, ...patch } : term) }))
  const moveTerm = (index: number, offset: -1 | 1) => setDraft((current) => {
    const target = index + offset
    if (target < 0 || target >= current.terms.length) return current
    const terms = [...current.terms]
    ;[terms[index], terms[target]] = [terms[target], terms[index]]
    return { ...current, terms }
  })
  const save = async () => {
    if (!editing) return
    setSaving(true); setError(null)
    const input = { ...draft, terms: draft.terms.map((term, index) => ({ ...term, sort_order: index })) }
    try {
      if (editing === 'new') await client.create(input)
      else await client.revise(editing.id, { label: input.label, description: input.description, allow_local_terms: input.allow_local_terms, terms: input.terms })
      setEditing(null); setMigration(null); load()
    } catch (cause) { setError(cause instanceof Error ? cause.message : translate('taxonomies.saveFailed')) } finally { setSaving(false) }
  }
  const previewMigration = async (apply: boolean) => {
    setSaving(true); setError(null)
    try { setMigration(await client.migration(apply)) } catch (cause) { setError(cause instanceof Error ? cause.message : translate('taxonomies.migrationFailed')) } finally { setSaving(false) }
  }

  return <>
    <header className="page-header"><div><h1>{translate('taxonomies.heading')}</h1><p>{translate('taxonomies.intro')}</p></div><button className="primary-button" type="button" onClick={() => start()}><Plus size={17} />{translate('taxonomies.new')}</button></header>
    {error && <div className="form-message error" role="alert">{error}</div>}
    {editing && <section className="content-section taxonomy-editor" aria-labelledby="taxonomy-editor-heading">
      <div className="section-heading"><h2 id="taxonomy-editor-heading">{editing === 'new' ? translate('taxonomies.new') : translate('taxonomies.newVersion')}</h2><button className="secondary-button" type="button" onClick={() => setEditing(null)}>{translate('common.cancel')}</button></div>
      <div className="document-detail-fields">
        <label>{translate('taxonomies.key')}<input value={draft.key} disabled={editing !== 'new'} maxLength={80} onChange={(event) => setDraft({ ...draft, key: event.target.value })} /></label>
        <label>{translate('taxonomies.binding')}<select value={draft.binding} disabled={editing !== 'new'} onChange={(event) => setDraft({ ...draft, binding: event.target.value as TaxonomyBinding })}>{bindingOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        <label>{translate('taxonomies.label')}<input value={draft.label} maxLength={120} onChange={(event) => setDraft({ ...draft, label: event.target.value })} /></label>
        <label>{translate('taxonomies.description')}<input value={draft.description} maxLength={500} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
      </div>
      <label className="checkbox-label"><input type="checkbox" checked={draft.allow_local_terms} onChange={(event) => setDraft({ ...draft, allow_local_terms: event.target.checked })} />{translate('taxonomies.allowLocal')}</label>
      <div className="section-heading"><h3>{translate('taxonomies.terms')}</h3><button className="secondary-button" type="button" onClick={() => setDraft({ ...draft, terms: [...draft.terms, emptyTerm()] })}><Plus size={15} />{translate('taxonomies.addTerm')}</button></div>
      <div className="taxonomy-term-list">
        {draft.terms.map((term, index) => <fieldset key={`${term.stable_key}-${index}`} className="taxonomy-term-row"><legend>{term.label || translate('taxonomies.termNumber', { number: index + 1 })}{editing !== 'new' && term.stable_key && <small>{translate('taxonomies.termUsage', editing.current_version.terms.find((existing) => existing.stable_key === term.stable_key)?.impact ?? { documents: 0, templates: 0 })}</small>}</legend><div className="document-detail-fields">
          <label>{translate('taxonomies.termKey')}<input value={term.stable_key} maxLength={80} onChange={(event) => updateTerm(index, { stable_key: event.target.value })} /></label>
          <label>{translate('taxonomies.termLabel')}<input value={term.label} maxLength={120} onChange={(event) => updateTerm(index, { label: event.target.value })} /></label>
          <label>{translate('taxonomies.parent')}<select value={term.parent_key} onChange={(event) => updateTerm(index, { parent_key: event.target.value })}><option value="">{translate('taxonomies.noParent')}</option>{draft.terms.filter((candidate, position) => position !== index && candidate.stable_key).map((candidate) => <option key={candidate.stable_key} value={candidate.stable_key}>{candidate.label || candidate.stable_key}</option>)}</select></label>
          <label>{translate('taxonomies.aliases')}<input value={term.aliases.join(', ')} maxLength={400} onChange={(event) => updateTerm(index, { aliases: event.target.value.split(',').map((value) => value.trim()).filter(Boolean) })} /></label>
          <label>{translate('taxonomies.status')}<select value={term.status} onChange={(event) => updateTerm(index, { status: event.target.value as TermDraft['status'] })}><option value="active">{translate('taxonomies.active')}</option><option value="retired">{translate('taxonomies.retired')}</option></select></label>
          <label>{translate('taxonomies.replacement')}<select value={term.replacement_key} disabled={term.status !== 'retired'} onChange={(event) => updateTerm(index, { replacement_key: event.target.value })}><option value="">{translate('taxonomies.noReplacement')}</option>{draft.terms.filter((candidate, position) => position !== index && candidate.stable_key && candidate.status === 'active').map((candidate) => <option key={candidate.stable_key} value={candidate.stable_key}>{candidate.label || candidate.stable_key}</option>)}</select></label>
        </div><label>{translate('taxonomies.termDescription')}<input value={term.description} maxLength={500} onChange={(event) => updateTerm(index, { description: event.target.value })} /></label><div className="row-actions"><button className="row-action" type="button" disabled={index === 0} onClick={() => moveTerm(index, -1)}><ArrowUp size={14} />{translate('taxonomies.moveUp')}</button><button className="row-action" type="button" disabled={index === draft.terms.length - 1} onClick={() => moveTerm(index, 1)}><ArrowDown size={14} />{translate('taxonomies.moveDown')}</button><button className="row-action danger" type="button" disabled={draft.terms.length === 1} onClick={() => setDraft({ ...draft, terms: draft.terms.filter((_, position) => position !== index) })}><Trash2 size={14} />{translate('common.remove')}</button></div></fieldset>)}
      </div>
      <button className="primary-button" type="button" disabled={saving || !draft.key || !draft.label || draft.terms.some((term) => !term.stable_key || !term.label)} onClick={() => { void save() }}>{saving ? translate('common.saving') : translate('taxonomies.save')}</button>
    </section>}
    <section className="content-section" aria-busy={phase === 'loading'}>
      <div className="section-heading"><h2>{translate('taxonomies.definitions')}</h2><span>{items.length}</span></div>
      {phase === 'loading' && <p className="empty-state">{translate('taxonomies.loading')}</p>}
      {phase === 'error' && <p className="empty-state">{translate('taxonomies.loadFailed')}</p>}
      {phase === 'ready' && items.length === 0 && <p className="empty-state">{translate('taxonomies.empty')}</p>}
      {items.length > 0 && <div className="taxonomy-table" role="table" aria-label={translate('taxonomies.definitions')}><div className="taxonomy-table-row header" role="row"><span role="columnheader">{translate('taxonomies.name')}</span><span role="columnheader">{translate('taxonomies.binding')}</span><span role="columnheader">{translate('taxonomies.version')}</span><span role="columnheader">{translate('taxonomies.usage')}</span><span role="columnheader">{translate('common.actions')}</span></div>{items.map((taxonomy) => <div className="taxonomy-table-row" role="row" key={taxonomy.id}><span role="cell"><strong>{taxonomy.current_version.label}</strong><code>{taxonomy.key}</code><small>{taxonomy.current_version.description}</small></span><span role="cell">{bindingOptions.find((option) => option.value === taxonomy.binding)?.label}</span><span role="cell">v{taxonomy.current_version.version} · {taxonomy.current_version.terms.length} {translate('taxonomies.terms').toLowerCase()}</span><span role="cell">{translate('taxonomies.usageCount', taxonomy.impact)}</span><span role="cell" className="row-actions"><button className="row-action" type="button" onClick={() => start(taxonomy)}>{translate('taxonomies.newVersion')}</button><button className="row-action danger" type="button" onClick={() => { if (window.confirm(translate('taxonomies.archiveConfirm', { name: taxonomy.current_version.label }))) void client.archive(taxonomy.id).then(load).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : translate('taxonomies.saveFailed'))) }}>{translate('common.archive')}</button></span></div>)}</div>}
    </section>
    <section className="content-section"><div className="section-heading"><div><h2>{translate('taxonomies.migration')}</h2><p>{translate('taxonomies.migrationIntro')}</p></div><button className="secondary-button" type="button" disabled={saving} onClick={() => { void previewMigration(false) }}>{translate('taxonomies.preview')}</button></div>{migration && <><p role="status">{translate('taxonomies.migrationSummary', migration.counts)}</p>{migration.rows.length > 0 && <div className="taxonomy-migration-list" role="table" aria-label={translate('taxonomies.migration')}><div className="taxonomy-migration-row header" role="row"><span role="columnheader">{translate('taxonomies.document')}</span><span role="columnheader">{translate('taxonomies.legacyTag')}</span><span role="columnheader">{translate('taxonomies.match')}</span></div>{migration.rows.map((row, index) => <div className="taxonomy-migration-row" role="row" key={`${row.document_id}-${row.tag}-${index}`}><span role="cell">{row.document_title}</span><span role="cell">{row.tag}</span><span role="cell">{row.term_label ?? row.status}</span></div>)}</div>}{migration.counts.matched > 0 && <button className="primary-button" type="button" disabled={saving} onClick={() => { void previewMigration(true) }}>{translate('taxonomies.applyMigration')}</button>}</>}
    </section>
  </>
}
