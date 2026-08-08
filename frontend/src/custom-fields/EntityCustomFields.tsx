import { useEffect, useMemo, useState } from 'react'
import type { WorkspaceContext } from '../workspaces/api'
import { browserCustomFieldsClient } from './api'
import type { CustomFieldVersion, CustomFieldsClient, EntityCustomField } from './api'

function options(version: CustomFieldVersion) {
  const direct = version.schema.enum
  const nested = typeof version.schema.items === 'object' && version.schema.items !== null ? (version.schema.items as Record<string, unknown>).enum : undefined
  return Array.isArray(direct) ? direct.map(String) : Array.isArray(nested) ? nested.map(String) : []
}
function errorMessage(error: unknown) { return error instanceof Error ? error.message : 'The custom-field change was not completed.' }

function ValueControl({ field, value, onChange }: { field: EntityCustomField; value: unknown; onChange: (value: unknown) => void }) {
  const version = field.definition.current_version
  if (version.field_type === 'boolean') return <select aria-label={version.label} value={value === true ? 'true' : value === false ? 'false' : ''} onChange={(event) => onChange(event.target.value === '' ? null : event.target.value === 'true')}><option value="">Not set</option><option value="true">Yes</option><option value="false">No</option></select>
  if (version.field_type === 'choice') return <select aria-label={version.label} value={typeof value === 'string' ? value : ''} onChange={(event) => onChange(event.target.value)}><option value="">Select…</option>{options(version).map((option) => <option key={option}>{option}</option>)}</select>
  if (version.field_type === 'multi_choice') {
    const selected = Array.isArray(value) ? value.map(String) : []
    return <fieldset><legend>{version.label}</legend>{options(version).map((option) => <label className="checkbox-label" key={option}><input type="checkbox" checked={selected.includes(option)} onChange={(event) => onChange(event.target.checked ? [...selected, option] : selected.filter((item) => item !== option))} />{option}</label>)}</fieldset>
  }
  const inputType = version.field_type === 'date' ? 'date' : version.field_type === 'url' ? 'url' : version.field_type === 'email' ? 'email' : version.field_type === 'integer' || version.field_type === 'number' ? 'number' : 'text'
  return <input aria-label={version.label} type={inputType} step={version.field_type === 'number' ? 'any' : undefined} value={typeof value === 'string' || typeof value === 'number' ? String(value) : ''} onChange={(event) => onChange(event.target.value === '' ? null : version.field_type === 'integer' ? Number.parseInt(event.target.value, 10) : version.field_type === 'number' ? Number.parseFloat(event.target.value) : event.target.value)} />
}

export function EntityCustomFields({ workspace, entityId, entityName, onClose, client = browserCustomFieldsClient }: { workspace: WorkspaceContext | null; entityId: string; entityName: string; onClose: () => void; client?: CustomFieldsClient }) {
  const scope = useMemo(() => workspace ? { organizationId: workspace.id } : {}, [workspace])
  const [fields, setFields] = useState<EntityCustomField[]>([])
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    void client.listEntityFields(scope, entityId, controller.signal).then((result) => {
      if (controller.signal.aborted) return
      setFields(result.fields); setValues(Object.fromEntries(result.fields.map((field) => [field.definition.id, field.value]))); setPhase('ready')
    }).catch((cause) => { if (!controller.signal.aborted) { setError(errorMessage(cause)); setPhase('error') } })
    return () => controller.abort()
  }, [client, entityId, scope])
  const save = async (field: EntityCustomField) => {
    setSaving(field.definition.id); setError(null)
    try {
      const value = values[field.definition.id]
      const result = await client.setEntityValue(scope, entityId, field.definition.id, value)
      setFields(result.fields); setValues(Object.fromEntries(result.fields.map((item) => [item.definition.id, item.value])))
    } catch (cause) { setError(errorMessage(cause)) } finally { setSaving(null) }
  }
  const clear = async (field: EntityCustomField) => {
    setSaving(field.definition.id); setError(null)
    try { await client.clearEntityValue(scope, entityId, field.definition.id); setValues((current) => ({ ...current, [field.definition.id]: null })); setFields((current) => current.map((item) => item.definition.id === field.definition.id ? { ...item, has_value: false, value: null, value_version: null, value_version_id: null, is_current: false, valid_for_current: true } : item)) }
    catch (cause) { setError(errorMessage(cause)) } finally { setSaving(null) }
  }
  return <section className="content-section entity-custom-fields" aria-labelledby="entity-custom-fields-heading" aria-busy={phase === 'loading'}><div className="section-heading"><h2 id="entity-custom-fields-heading">Custom fields for {entityName}</h2><button className="secondary-button" type="button" onClick={onClose}>Close</button></div>{error && <div className="form-message error" role="alert">{error}</div>}{phase === 'loading' && <p className="empty-state">Loading custom fields…</p>}{phase === 'error' && <p className="empty-state">Custom fields are unavailable.</p>}{phase === 'ready' && fields.length === 0 && <p className="empty-state">No custom fields apply to this record. Add one from Custom Fields in the navigation.</p>}{phase === 'ready' && fields.length > 0 && <div className="entity-custom-field-list">{fields.map((field) => {
        const control = <ValueControl field={field} value={values[field.definition.id]} onChange={(value) => setValues((current) => ({ ...current, [field.definition.id]: value }))} />
        return <div className="entity-custom-field" key={field.definition.id}><div>{field.definition.current_version.field_type === 'multi_choice' ? control : <label>{field.definition.current_version.label}{control}</label>}{field.definition.current_version.description && <p>{field.definition.current_version.description}</p>}{field.has_value && (!field.is_current || !field.valid_for_current) && <p className="field-version-warning" role="status">Stored with version {field.value_version}; review and save against version {field.definition.current_version.version}.</p>}{field.definition.archived && <p className="field-version-warning">This definition is archived. Its historical value is read-only.</p>}</div><div className="form-actions"><button className="primary-button" type="button" disabled={saving !== null || field.definition.archived || values[field.definition.id] === null} onClick={() => { void save(field) }}>{saving === field.definition.id ? 'Saving…' : 'Save'}</button>{field.has_value && <button className="secondary-button" type="button" disabled={saving !== null} onClick={() => { void clear(field) }}>Clear</button>}</div></div>
      })}</div>}</section>
}
