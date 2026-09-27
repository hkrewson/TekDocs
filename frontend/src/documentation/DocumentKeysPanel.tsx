import { Search, Trash2, X } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { DocumentKeyBinding, DocumentKeyReport, EntityMentionOption, WorkspaceKeyBinding } from './api'

type DocumentKeysPanelProps = {
  bindingMatches: WorkspaceKeyBinding[]
  bindingName: string
  bindingNameValid: boolean
  bindingQuery: string
  busy: boolean
  keyBindings: DocumentKeyBinding[]
  keyReport: DocumentKeyReport | null
  mentionOptions: EntityMentionOption[]
  mentionQuery: string
  bindingTargetable: (entityType: string) => boolean
  onBindingNameChange: (value: string) => void
  onBindingQueryChange: (value: string) => void
  onClose: () => void
  onDeclareBinding: (entity: EntityMentionOption) => void
  onInsertKey: (binding: DocumentKeyBinding, path: string) => void
  onMentionQueryChange: (value: string) => void
  onRetireBinding: (bindingId: string) => void
}

export function DocumentKeysPanel({
  bindingMatches,
  bindingName,
  bindingNameValid,
  bindingQuery,
  busy,
  keyBindings,
  keyReport,
  mentionOptions,
  mentionQuery,
  bindingTargetable,
  onBindingNameChange,
  onBindingQueryChange,
  onClose,
  onDeclareBinding,
  onInsertKey,
  onMentionQueryChange,
  onRetireBinding,
}: DocumentKeysPanelProps) {
  return <section className="document-context-panel document-keys" aria-labelledby="document-keys-heading">
    <div className="section-heading">
      <div><h2 id="document-keys-heading">{translate('documentation.keysPanel')}</h2></div>
      <button className="icon-button" type="button" aria-label={translate('documentation.closeKeys')} onClick={onClose}><X size={16} /></button>
    </div>
    <div className="entity-mention-picker">
      <label>
        <span>{translate('documentation.declareBinding')}</span>
        <input type="text" value={bindingName} onChange={(event) => onBindingNameChange(event.target.value.toLowerCase())} placeholder="subject" aria-label={translate('documentation.declareBinding')} aria-describedby="binding-name-rule" aria-invalid={bindingName.length > 0 && !bindingNameValid} />
      </label>
      <p id="binding-name-rule" className="field-hint" role={bindingName.length > 0 && !bindingNameValid ? 'alert' : undefined}>{translate('documentation.bindingNameRule')}</p>
      <label>
        <Search size={15} />
        <span>{translate('documentation.tekdocsRecord')}</span>
        <input type="search" value={mentionQuery} onChange={(event) => onMentionQueryChange(event.target.value)} />
      </label>
      {mentionOptions.length > 0 && <ul>{mentionOptions.map((entity) => {
        const targetable = bindingTargetable(entity.entity_type)
        return <li key={entity.id}>
          <button type="button" disabled={busy || !bindingNameValid || !targetable} onClick={() => onDeclareBinding(entity)}>
            <strong>{entity.display_name}</strong>
            <small>{targetable ? `${entity.entity_type.replaceAll('_', ' ')} · ${entity.workspace_label}` : translate('documentation.recordNotAddressable')}</small>
          </button>
        </li>
      })}</ul>}
    </div>
    {keyBindings.length > 0 && <div className="key-bindings" role="group" aria-label={translate('documentation.keyBindingsTable')}>
      <ul>{keyBindings.map((binding) => <li key={binding.id}>
        <span>
          <strong>{binding.name}</strong>
          <small>{binding.target_display_name} · {binding.target_entity_type.replaceAll('_', ' ')}</small>
          {binding.also_bound_by.length > 0 && <small className="key-where-used">{translate('documentation.alsoUsedBy')}: {binding.also_bound_by.map((item) => item.title).join(', ')}</small>}
        </span>
        <div>
          <label className="sr-only" htmlFor={`key-field-${binding.id}`}>{binding.name}</label>
          <select id={`key-field-${binding.id}`} defaultValue="" onChange={(event) => { if (event.target.value) { onInsertKey(binding, event.target.value); event.target.value = '' } }}>
            <option value="">{translate('documentation.insertKey')}</option>
            {binding.addressable_fields.map((path) => <option key={path} value={path}>{path}</option>)}
          </select>
          <button className="icon-button" type="button" aria-label={`${translate('documentation.retireBinding')} ${binding.name}`} disabled={busy} onClick={() => onRetireBinding(binding.id)}><Trash2 size={15} /></button>
        </div>
      </li>)}</ul>
    </div>}
    {keyReport && keyReport.count > 0 && <div className="key-report" role="group" aria-label={translate('documentation.keyReportTable')}>
      <ul>{keyReport.results.map((row) => <li key={row.expression} data-key-state={row.state}>
        <span><strong>{row.expression}</strong><small>{row.state === 'resolved' ? row.label : `${row.label} · ${row.reason ?? row.state}`}</small></span>
      </li>)}</ul>
    </div>}
    {keyReport && keyReport.count === 0 && <p className="empty-state">{translate('documentation.keysPanel')}</p>}
    <div className="key-browser">
      <label><Search size={15} /><span>{translate('documentation.findBindings')}</span><input type="search" value={bindingQuery} onChange={(event) => onBindingQueryChange(event.target.value)} /></label>
      {bindingMatches.length > 0 && <ul aria-label={translate('documentation.bindingBrowserTable')}>{bindingMatches.map((match) => <li key={match.id}>
        <span><strong>{match.target_display_name}</strong><small>{match.document_title} · {match.name}</small></span>
      </li>)}</ul>}
    </div>
  </section>
}
