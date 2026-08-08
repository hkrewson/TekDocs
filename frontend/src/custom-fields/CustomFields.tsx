import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import type { WorkspaceContext } from '../workspaces/api'
import { browserCustomFieldsClient } from './api'
import type { CustomFieldDefinition, CustomFieldDefinitionInput, CustomFieldEntityType, CustomFieldType, CustomFieldsClient, MigrationImpact } from './api'

const fieldTypeLabels: Record<CustomFieldType, string> = {
  text: 'Text', integer: 'Integer', number: 'Number', boolean: 'Yes / no', date: 'Date', url: 'URL', email: 'Email', choice: 'Choice', multi_choice: 'Multiple choice',
}
const entityTypeLabels: Record<CustomFieldEntityType, string> = { organization: 'Organization', person: 'Person', site: 'Site', location: 'Location' }
const emptyInput: CustomFieldDefinitionInput = { key: '', entity_type: 'site', label: '', description: '', required: false, field_type: 'text', display_order: 0, options: [] }

function message(error: unknown, fallback: string) { return error instanceof Error ? error.message : fallback }
function optionsFor(definition: CustomFieldDefinition) {
  const schema = definition.current_version.schema
  const direct = schema.enum
  const nested = typeof schema.items === 'object' && schema.items !== null ? (schema.items as Record<string, unknown>).enum : undefined
  return Array.isArray(direct) ? direct.map(String) : Array.isArray(nested) ? nested.map(String) : []
}

function DefinitionForm({ definition, organization, saving, onCancel, onSave }: {
  definition: CustomFieldDefinition | null
  organization: boolean
  saving: boolean
  onCancel: () => void
  onSave: (input: CustomFieldDefinitionInput) => Promise<void>
}) {
  const [input, setInput] = useState<CustomFieldDefinitionInput>(() => definition ? {
    key: definition.key,
    entity_type: definition.entity_type,
    label: definition.current_version.label,
    description: definition.current_version.description,
    required: definition.current_version.required,
    field_type: definition.current_version.field_type,
    display_order: definition.current_version.display_order,
    options: optionsFor(definition),
  } : emptyInput)
  const [choiceText, setChoiceText] = useState(() => input.options.join('\n'))
  const isChoice = input.field_type === 'choice' || input.field_type === 'multi_choice'
  const submit = (event: FormEvent) => {
    event.preventDefault()
    void onSave({ ...input, options: isChoice ? choiceText.split('\n').map((item) => item.trim()).filter(Boolean) : [] })
  }
  return (
    <section className="content-section custom-field-form-section" aria-labelledby="custom-field-form-heading">
      <div className="section-heading"><h2 id="custom-field-form-heading">{definition ? `Create version ${definition.current_version.version + 1}` : 'Add custom field'}</h2></div>
      <form className="custom-field-form" onSubmit={submit}>
        <label>Label<input autoFocus required maxLength={160} value={input.label} onChange={(event) => setInput({ ...input, label: event.target.value })} /></label>
        <label>Stable key<input required disabled={Boolean(definition)} pattern="[a-z][a-z0-9_-]*" maxLength={80} value={input.key} onChange={(event) => setInput({ ...input, key: event.target.value.toLowerCase().replace(/\s+/g, '_') })} /></label>
        <label>Record type<select disabled={Boolean(definition)} value={input.entity_type} onChange={(event) => setInput({ ...input, entity_type: event.target.value as CustomFieldEntityType })}>{(organization ? ['site', 'location'] : ['organization', 'person', 'site', 'location']).map((type) => <option key={type} value={type}>{entityTypeLabels[type as CustomFieldEntityType]}</option>)}</select></label>
        <label>Field type<select value={input.field_type} onChange={(event) => setInput({ ...input, field_type: event.target.value as CustomFieldType })}>{Object.entries(fieldTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Display order<input type="number" min={-1000} max={1000} value={input.display_order} onChange={(event) => setInput({ ...input, display_order: Number(event.target.value) })} /></label>
        <label className="checkbox-label"><input type="checkbox" checked={input.required} onChange={(event) => setInput({ ...input, required: event.target.checked })} />Required when an integrated form collects this field</label>
        <label className="custom-field-form-wide">Help text<textarea maxLength={500} rows={2} value={input.description} onChange={(event) => setInput({ ...input, description: event.target.value })} /></label>
        {isChoice && <label className="custom-field-form-wide">Choices <span>One per line</span><textarea required rows={5} value={choiceText} onChange={(event) => setChoiceText(event.target.value)} /></label>}
        <div className="form-actions custom-field-form-wide"><button className="primary-button" disabled={saving}>{saving ? 'Saving…' : definition ? 'Create version' : 'Add field'}</button><button className="secondary-button" type="button" disabled={saving} onClick={onCancel}>Cancel</button></div>
      </form>
    </section>
  )
}

export function CustomFields({ workspace, client = browserCustomFieldsClient }: { workspace: WorkspaceContext | null; client?: CustomFieldsClient }) {
  const scope = useMemo(() => workspace ? { organizationId: workspace.id } : {}, [workspace])
  const scopeKey = workspace?.id ?? 'msp'
  const [definitions, setDefinitions] = useState<CustomFieldDefinition[]>([])
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<CustomFieldDefinition | null | undefined>(undefined)
  const [archiving, setArchiving] = useState<CustomFieldDefinition | null>(null)
  const [saving, setSaving] = useState(false)
  const [impact, setImpact] = useState<MigrationImpact | null>(null)

  const load = async (signal?: AbortSignal) => {
    setPhase('loading'); setError(null); setDefinitions([])
    try {
      const result = await client.listDefinitions(scope, signal)
      if (!signal?.aborted) { setDefinitions(result.results); setPhase('ready') }
    } catch (cause) {
      if (!signal?.aborted) { setError(message(cause, 'Custom fields could not be loaded.')); setPhase('error') }
    }
  }
  useEffect(() => {
    const controller = new AbortController()
    void client.listDefinitions(scope, controller.signal).then((result) => {
      if (!controller.signal.aborted) { setDefinitions(result.results); setPhase('ready') }
    }).catch((cause) => {
      if (!controller.signal.aborted) { setError(message(cause, 'Custom fields could not be loaded.')); setPhase('error') }
    })
    return () => controller.abort()
  }, [client, scope, scopeKey])

  const save = async (input: CustomFieldDefinitionInput) => {
    setSaving(true); setError(null); setImpact(null)
    try {
      if (editing) {
        const result = await client.createVersion(scope, editing.id, input)
        setImpact(result.migration_impact)
      } else {
        await client.createDefinition(scope, input)
      }
      setEditing(undefined); await load()
    } catch (cause) { setError(message(cause, 'The custom field was not saved.')) } finally { setSaving(false) }
  }
  const archive = async () => {
    if (!archiving) return
    setSaving(true); setError(null)
    try { await client.archiveDefinition(scope, archiving.id); setArchiving(null); await load() }
    catch (cause) { setError(message(cause, 'The custom field was not archived.')) } finally { setSaving(false) }
  }

  return (
    <>
      <header className="page-header"><div><h1>Custom fields</h1><p>Extend records with validated fields while preserving the version used by existing values.</p></div><button className="primary-button" type="button" onClick={() => { setEditing(null); setImpact(null) }}><Plus size={16} />New field</button></header>
      {editing !== undefined && <DefinitionForm key={editing?.id ?? `new-${scopeKey}`} definition={editing} organization={Boolean(workspace)} saving={saving} onCancel={() => setEditing(undefined)} onSave={save} />}
      {error && <div className="form-message error" role="alert">{error}</div>}
      {impact && <div className={`form-message${impact.incompatible ? ' warning' : ' success'}`} role="status">Version created. {impact.compatible} existing value{impact.compatible === 1 ? '' : 's'} remain compatible; {impact.incompatible} require review. Existing values were not changed.</div>}
      <section className="content-section" aria-busy={phase === 'loading'}>
        <div className="section-heading"><h2>Definitions</h2><span>{workspace ? `${workspace.name} and inherited MSP fields` : 'MSP-wide fields'}</span></div>
        {phase === 'loading' && <p className="empty-state">Loading custom fields…</p>}
        {phase === 'error' && <p className="empty-state">Custom fields are unavailable. Use the message above to retry after correcting the problem.</p>}
        {phase === 'ready' && definitions.length === 0 && <p className="empty-state">No custom fields have been defined for this workspace.</p>}
        {phase === 'ready' && definitions.length > 0 && <div className="custom-field-table" role="table" aria-label="Custom-field definitions">
          <div className="custom-field-row header" role="row"><span role="columnheader">Field</span><span role="columnheader">Applies to</span><span role="columnheader">Type</span><span role="columnheader">Version</span><span role="columnheader">Scope</span><span role="columnheader">Actions</span></div>
          {definitions.map((definition) => <div className="custom-field-row" role="row" key={definition.id}>
            <span role="cell"><strong>{definition.current_version.label}</strong><code>{definition.key}</code>{definition.current_version.description && <span>{definition.current_version.description}</span>}</span>
            <span role="cell">{entityTypeLabels[definition.entity_type]}</span>
            <span role="cell">{fieldTypeLabels[definition.current_version.field_type]}</span>
            <span role="cell"><details><summary>v{definition.current_version.version}</summary><ol>{[...definition.versions].reverse().map((version) => <li key={version.id}>v{version.version} · {version.label}</li>)}</ol></details></span>
            <span role="cell">{definition.inherited ? 'Inherited from MSP' : definition.owner === 'msp' ? 'MSP-wide' : 'This organization'}</span>
            <span role="cell" className="row-actions">{definition.inherited ? <span>Managed by MSP</span> : <><button className="row-action" type="button" onClick={() => { setEditing(definition); setImpact(null) }}><Pencil size={14} />New version</button><button className="row-action danger" type="button" onClick={() => setArchiving(definition)}><Trash2 size={14} />Archive</button></>}</span>
          </div>)}
        </div>}
      </section>
      {archiving && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-custom-field-heading"><div><strong id="archive-custom-field-heading">Archive {archiving.current_version.label}?</strong><p>Existing values and all definition versions remain available for history. New values will be blocked.</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? 'Archiving…' : 'Archive'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setArchiving(null)}>Cancel</button></div></div>}
    </>
  )
}
