import { Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { useSearchParams } from 'react-router'

import { CollectionPagination } from '../CollectionPagination'
import { FilterMenu } from '../FilterMenu'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import { browserCustomFieldsClient } from './api'
import type { CustomFieldDefinition, CustomFieldDefinitionInput, CustomFieldEntityType, CustomFieldType, CustomFieldsClient, MigrationImpact } from './api'

const fieldTypeLabels: Record<CustomFieldType, string> = {
  text: translate('customFields.typeText'), integer: translate('customFields.typeInteger'), number: translate('customFields.typeNumber'), boolean: translate('customFields.typeBoolean'),
  date: translate('customFields.typeDate'), url: translate('customFields.typeUrl'), email: translate('customFields.typeEmail'), choice: translate('customFields.typeChoice'), multi_choice: translate('customFields.typeMultipleChoice'),
}
const entityTypeLabels: Record<CustomFieldEntityType, string> = {
  organization: translate('customFields.recordOrganization'), person: translate('customFields.recordPerson'), site: translate('customFields.recordSite'), location: translate('customFields.recordLocation'),
}
const emptyInput: CustomFieldDefinitionInput = { key: '', entity_type: 'site', label: '', description: '', required: false, field_type: 'text', display_order: 0, options: [] }
const pageSizes = [25, 50, 100] as const

function message(error: unknown, fallback: string) { return error instanceof Error ? error.message : fallback }
function pageFrom(value: string | null) { const parsed = Number(value); return Number.isInteger(parsed) && parsed > 0 ? parsed : 1 }
function pageSizeFrom(value: string | null): typeof pageSizes[number] { const parsed = Number(value); return pageSizes.includes(parsed as typeof pageSizes[number]) ? parsed as typeof pageSizes[number] : 25 }
function entityFrom(value: string | null): CustomFieldEntityType | '' { return value && value in entityTypeLabels ? value as CustomFieldEntityType : '' }
function optionsFor(definition: CustomFieldDefinition) {
  const schema = definition.current_version.schema
  const direct = schema.enum
  const nested = typeof schema.items === 'object' && schema.items !== null ? (schema.items as Record<string, unknown>).enum : undefined
  return Array.isArray(direct) ? direct.map(String) : Array.isArray(nested) ? nested.map(String) : []
}
function versionCreatedMessage(impact: MigrationImpact) {
  if (impact.compatible === 1 && impact.incompatible === 1) return translate('customFields.versionCreatedOneOne')
  if (impact.compatible === 1) return translate('customFields.versionCreatedOneMany', { incompatible: impact.incompatible })
  if (impact.incompatible === 1) return translate('customFields.versionCreatedManyOne', { compatible: impact.compatible })
  return translate('customFields.versionCreatedManyMany', { compatible: impact.compatible, incompatible: impact.incompatible })
}

function DefinitionForm({ definition, organization, saving, closingAfterSave, onCancel, onSave }: {
  definition: CustomFieldDefinition | null
  organization: boolean
  saving: boolean
  closingAfterSave: boolean
  onCancel: () => void
  onSave: (input: CustomFieldDefinitionInput) => Promise<void>
}) {
  const initial = useMemo<CustomFieldDefinitionInput>(() => definition ? {
    key: definition.key, entity_type: definition.entity_type, label: definition.current_version.label,
    description: definition.current_version.description, required: definition.current_version.required,
    field_type: definition.current_version.field_type, display_order: definition.current_version.display_order,
    options: optionsFor(definition),
  } : emptyInput, [definition])
  const [input, setInput] = useState(initial)
  const [choiceText, setChoiceText] = useState(() => initial.options.join('\n'))
  const isChoice = input.field_type === 'choice' || input.field_type === 'multi_choice'
  const dirty = JSON.stringify(input) !== JSON.stringify(initial) || choiceText !== initial.options.join('\n')
  const attempt = useUnsavedChanges(dirty && !closingAfterSave, saving && !closingAfterSave, undefined, !closingAfterSave)
  useEffect(() => {
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = overflow }
  }, [])
  const submit = (event: FormEvent) => {
    event.preventDefault()
    void onSave({ ...input, options: isChoice ? choiceText.split('\n').map((item) => item.trim()).filter(Boolean) : [] })
  }
  return <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="custom-field-form-heading">
    <form className="record-form record-form-grid custom-field-form" onSubmit={submit}>
      <div className="section-heading"><div><h2 id="custom-field-form-heading">{definition ? translate('customFields.createVersionHeading', { version: definition.current_version.version + 1, name: definition.current_version.label }) : translate('customFields.add')}</h2>{definition && <p>{translate('customFields.versionHelp')}</p>}</div></div>
      <label>{translate('customFields.label')}<input autoFocus required maxLength={160} value={input.label} onChange={(event) => setInput({ ...input, label: event.target.value })} /></label>
      <label>{translate('customFields.fieldKey')} <span>{translate('customFields.fieldKeyHelp')}</span><input required disabled={Boolean(definition)} pattern="[a-z][a-z0-9_-]*" maxLength={80} value={input.key} onChange={(event) => setInput({ ...input, key: event.target.value.toLowerCase().replace(/\s+/g, '_') })} /></label>
      <label>{translate('customFields.recordType')}<select disabled={Boolean(definition)} value={input.entity_type} onChange={(event) => setInput({ ...input, entity_type: event.target.value as CustomFieldEntityType })}>{(organization ? ['site', 'location'] : ['organization', 'person', 'site', 'location']).map((type) => <option key={type} value={type}>{entityTypeLabels[type as CustomFieldEntityType]}</option>)}</select></label>
      <label>{translate('customFields.fieldType')}<select value={input.field_type} onChange={(event) => setInput({ ...input, field_type: event.target.value as CustomFieldType })}>{Object.entries(fieldTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>{translate('customFields.listOrder')}<input type="number" min={-1000} max={1000} value={input.display_order} onChange={(event) => setInput({ ...input, display_order: Number(event.target.value) })} /></label>
      <label className="checkbox-label"><input type="checkbox" checked={input.required} onChange={(event) => setInput({ ...input, required: event.target.checked })} />{translate('customFields.required')}</label>
      <label className="custom-field-form-wide">{translate('customFields.helpText')}<textarea maxLength={500} rows={2} value={input.description} onChange={(event) => setInput({ ...input, description: event.target.value })} /></label>
      {isChoice && <label className="custom-field-form-wide">{translate('customFields.choices')} <span>{translate('customFields.onePerLine')}</span><textarea required rows={5} value={choiceText} onChange={(event) => setChoiceText(event.target.value)} /></label>}
      <div className="form-actions custom-field-form-wide"><button className="primary-button" disabled={saving}>{saving ? translate('common.saving') : definition ? translate('customFields.createVersion') : translate('customFields.addButton')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => attempt(onCancel)}>{translate('common.cancel')}</button></div>
    </form>
  </section>
}

export function CustomFields({ workspace, client = browserCustomFieldsClient }: { workspace: WorkspaceContext | null; client?: CustomFieldsClient }) {
  const scope = useMemo(() => workspace ? { organizationId: workspace.id } : {}, [workspace])
  const scopeKey = workspace?.id ?? 'msp'
  const [parameters, setParameters] = useSearchParams()
  const query = parameters.get('q') ?? ''
  const entityType = entityFrom(parameters.get('entity_type'))
  const page = pageFrom(parameters.get('page'))
  const pageSize = pageSizeFrom(parameters.get('page_size'))
  const editorId = parameters.get('field')
  const [definitions, setDefinitions] = useState<CustomFieldDefinition[]>([])
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [archiving, setArchiving] = useState<CustomFieldDefinition | null>(null)
  const [saving, setSaving] = useState(false)
  const [closingAfterSave, setClosingAfterSave] = useState(false)
  const [impact, setImpact] = useState<MigrationImpact | null>(null)
  const [revision, setRevision] = useState(0)

  function updateParameters(changes: Record<string, string | number | null>, replace = false) {
    setParameters((current) => {
      const next = new URLSearchParams(current)
      for (const [key, value] of Object.entries(changes)) {
        if (value === null || value === '' || key === 'page' && value === 1 || key === 'page_size' && value === 25) next.delete(key)
        else next.set(key, String(value))
      }
      return next
    }, { replace })
  }
  const load = async (signal?: AbortSignal) => {
    setPhase('loading'); setError(null)
    try {
      const result = await client.listDefinitions(scope, signal)
      if (!signal?.aborted) { setDefinitions(result.results); setPhase('ready') }
    } catch (cause) {
      if (!signal?.aborted) { setError(message(cause, translate('customFields.loadFailed'))); setPhase('error') }
    }
  }
  useEffect(() => {
    const controller = new AbortController()
    void client.listDefinitions(scope, controller.signal).then((result) => {
      if (!controller.signal.aborted) { setDefinitions(result.results); setPhase('ready') }
    }).catch((cause) => {
      if (!controller.signal.aborted) { setError(message(cause, translate('customFields.loadFailed'))); setPhase('error') }
    })
    return () => controller.abort()
  }, [client, revision, scope, scopeKey])

  const filtered = definitions.filter((definition) => {
    const text = `${definition.current_version.label} ${definition.key} ${definition.current_version.description}`.toLowerCase()
    return (!query || text.includes(query.toLowerCase())) && (!entityType || definition.entity_type === entityType)
  })
  const first = (page - 1) * pageSize
  const visible = filtered.slice(first, first + pageSize)
  const editing = editorId === 'new' ? null : definitions.find((item) => item.id === editorId)

  const save = async (input: CustomFieldDefinitionInput) => {
    setSaving(true); setError(null); setImpact(null)
    try {
      if (editing) {
        const result = await client.createVersion(scope, editing.id, input)
        setImpact(result.migration_impact)
      } else await client.createDefinition(scope, input)
      setClosingAfterSave(true)
      window.setTimeout(() => { updateParameters({ field: null }); setClosingAfterSave(false) }, 50)
      await load()
    } catch (cause) { setError(message(cause, translate('customFields.saveFailed'))) } finally { setSaving(false) }
  }
  const archive = async () => {
    if (!archiving) return
    setSaving(true); setError(null)
    try { await client.archiveDefinition(scope, archiving.id); setArchiving(null); await load() }
    catch (cause) { setError(message(cause, translate('customFields.archiveFailed'))) } finally { setSaving(false) }
  }

  return <>
    <header className="page-header"><div><h1>{translate('customFields.heading')}</h1><p>{translate('customFields.headingHelp')}</p></div><button className="primary-button" type="button" aria-label={translate('customFields.new')} title={translate('customFields.new')} onClick={() => { setClosingAfterSave(false); updateParameters({ field: 'new' }); setImpact(null) }}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('customFields.new')}</span></button></header>
    {editorId && (editorId === 'new' || editing) && <DefinitionForm key={`${scopeKey}:${editorId}`} definition={editing ?? null} organization={Boolean(workspace)} saving={saving} closingAfterSave={closingAfterSave} onCancel={() => updateParameters({ field: null })} onSave={save} />}
    {editorId && editorId !== 'new' && phase === 'ready' && !editing && <div className="form-message warning" role="alert">{translate('customFields.fieldUnavailable')} <button className="row-action" type="button" onClick={() => updateParameters({ field: null })}>{translate('common.close')}</button></div>}
    {error && phase !== 'error' && <div className="form-message error" role="alert">{error}</div>}
    {impact && <div className={`form-message${impact.incompatible ? ' warning' : ' success'}`} role="status">{versionCreatedMessage(impact)}</div>}
    <section className="content-section" aria-busy={phase === 'loading'}>
      <div className="section-heading"><h2>{translate('customFields.list')}</h2><span>{translate('customFields.count', { count: filtered.length })}</span></div>
      <div className="collection-toolbar metadata-toolbar">
        <label className="collection-search"><Search size={16} aria-hidden="true" /><span className="sr-only">{translate('customFields.search')}</span><input type="search" value={query} placeholder={translate('customFields.search')} onChange={(event) => updateParameters({ q: event.target.value, page: 1 }, true)} /></label>
        <FilterMenu groups={[{ kind: 'choices', label: translate('customFields.recordType'), value: entityType, choices: [{ value: '', label: translate('customFields.allRecordTypes') }, ...Object.entries(entityTypeLabels).map(([value, label]) => ({ value, label }))], onChange: (value) => updateParameters({ entity_type: value, page: 1 }) }]} activeCount={entityType ? 1 : 0} onClear={() => updateParameters({ entity_type: null, page: 1 })} />
        <label className="collection-page-size">{translate('collections.pageSize')}<select value={pageSize} onChange={(event) => updateParameters({ page_size: Number(event.target.value), page: 1 })}>{pageSizes.map((size) => <option key={size} value={size}>{size}</option>)}</select></label>
      </div>
      {(query || entityType) && <div className="collection-active-filters">{query && <button className="row-action" type="button" onClick={() => updateParameters({ q: null, page: 1 })}>{translate('customFields.searchSummary', { query })} ×</button>}{entityType && <button className="row-action" type="button" onClick={() => updateParameters({ entity_type: null, page: 1 })}>{entityTypeLabels[entityType]} ×</button>}</div>}
      {phase === 'loading' && <p className="empty-state" role="status">{translate('customFields.loading')}</p>}
      {phase === 'error' && <div className="empty-state" role="alert"><p>{error ?? translate('customFields.unavailable')}</p><button className="secondary-button" type="button" onClick={() => { setPhase('loading'); setError(null); setRevision((value) => value + 1) }}>{translate('common.retry')}</button></div>}
      {phase === 'ready' && filtered.length === 0 && <p className="empty-state">{query || entityType ? translate('customFields.noMatches') : translate('customFields.empty')}</p>}
      {phase === 'ready' && visible.length > 0 && <ol className="plain-detail-list metadata-list">{visible.map((definition) => <li key={definition.id}>
        <div><strong>{definition.current_version.label}</strong><span><code>{definition.key}</code> · {entityTypeLabels[definition.entity_type]} · {fieldTypeLabels[definition.current_version.field_type]}</span><span>{definition.inherited ? translate('customFields.fromMsp') : definition.owner === 'msp' ? translate('customFields.allWorkspaces') : translate('customFields.thisWorkspace')} · {translate('customFields.versionSummary', { version: definition.current_version.version })}</span>{definition.current_version.description && <span>{definition.current_version.description}</span>}<details><summary>{translate('customFields.versionHistory')}</summary><ol>{[...definition.versions].reverse().map((version) => <li key={version.id}>v{version.version} · {version.label}</li>)}</ol></details></div>
        <div className="row-actions">{definition.inherited ? <span>{translate('customFields.editFromMsp')}</span> : <><button className="row-action" type="button" aria-label={translate('customFields.newVersionFor', { name: definition.current_version.label })} onClick={() => { setClosingAfterSave(false); updateParameters({ field: definition.id }); setImpact(null) }}><Pencil size={14} aria-hidden="true" />{translate('customFields.newVersion')}</button><button className="row-action danger" type="button" aria-label={translate('customFields.archiveField', { name: definition.current_version.label })} onClick={() => setArchiving(definition)}><Trash2 size={14} aria-hidden="true" />{translate('common.archive')}</button></>}</div>
      </li>)}</ol>}
      <CollectionPagination label={translate('customFields.list')} page={page} pageSize={pageSize} count={filtered.length} hasMore={first + pageSize < filtered.length} onPageChange={(nextPage) => updateParameters({ page: nextPage })} />
    </section>
    {archiving && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-custom-field-heading"><div><strong id="archive-custom-field-heading">{translate('customFields.archiveQuestion', { name: archiving.current_version.label })}</strong><p>{translate('customFields.archiveHelp')}</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? translate('common.archiving') : translate('common.archive')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setArchiving(null)}>{translate('common.cancel')}</button></div></div>}
  </>
}
