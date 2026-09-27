import { Search, X } from 'lucide-react'
import { translate } from '../i18n/localization'
import { BlockLibrary } from './BlockLibrary'
import { DocumentLinkPicker } from './DocumentLinkPicker'
import type {
  BlockLibraryItem,
  DocumentRecord,
  DocumentScope,
  DocumentsClient,
  EntityMentionOption,
  PlacementAudienceProfile,
} from './api'

type DocumentReusePanelProps = {
  audience: PlacementAudienceProfile
  busy: boolean
  client: DocumentsClient
  documentId: string
  mentionOptions: EntityMentionOption[]
  mentionQuery: string
  mode: 'live' | 'pinned'
  scope: DocumentScope
  onAudienceChange: (audience: PlacementAudienceProfile) => void
  onClose: () => void
  onDocumentInsert: (document: DocumentRecord) => void
  onMentionInsert: (entity: EntityMentionOption) => void
  onMentionQueryChange: (value: string) => void
  onModeChange: (mode: 'live' | 'pinned') => void
  onReusableBlockInsert: (block: BlockLibraryItem) => void
}

export function DocumentReusePanel({
  audience,
  busy,
  client,
  documentId,
  mentionOptions,
  mentionQuery,
  mode,
  scope,
  onAudienceChange,
  onClose,
  onDocumentInsert,
  onMentionInsert,
  onMentionQueryChange,
  onModeChange,
  onReusableBlockInsert,
}: DocumentReusePanelProps) {
  return <section className="document-context-panel" aria-labelledby="insert-existing-heading">
    <div className="section-heading">
      <div>
        <h2 id="insert-existing-heading">{translate('documentation.insertExisting')}</h2>
        <p>{translate('documentation.insertExistingHelp')}</p>
      </div>
      <button className="icon-button" type="button" aria-label={translate('documentation.closeExisting')} onClick={onClose}><X size={16} /></button>
    </div>
    <div className="reuse-resolution">
      <label>
        {translate('documentation.whenSourceChanges')}
        <select value={mode} onChange={(event) => onModeChange(event.target.value as 'live' | 'pinned')}>
          <option value="live">{translate('documentation.useLatest')}</option>
          <option value="pinned">{translate('documentation.keepThisVersion')}</option>
        </select>
      </label>
      <label>
        {translate('documentation.audienceLabel')}
        <select value={audience} onChange={(event) => onAudienceChange(event.target.value as PlacementAudienceProfile)}>
          <option value="shared">{translate('documentation.audienceShared')}</option>
          <option value="msp_internal">{translate('documentation.audienceMspInternal')}</option>
          <option value="client_visible">{translate('documentation.audienceClientVisible')}</option>
        </select>
      </label>
    </div>
    <BlockLibrary key={documentId} scope={scope} documentId={documentId} client={client} busy={busy} onInsert={onReusableBlockInsert} />
    <DocumentLinkPicker key={`document-${documentId}`} scope={scope} documentId={documentId} client={client} busy={busy} onInsert={onDocumentInsert} />
    <div className="entity-mention-picker">
      <label>
        <Search size={15} />
        <span>{translate('documentation.linkRecord')}</span>
        <input type="search" placeholder={translate('documentation.searchRecords')} value={mentionQuery} onChange={(event) => onMentionQueryChange(event.target.value)} />
      </label>
      {mentionOptions.length > 0 && <ul>{mentionOptions.map((entity) => <li key={entity.id}>
        <button type="button" onClick={() => onMentionInsert(entity)}>
          <strong>{entity.display_name}</strong>
          <small>{entity.entity_type.replaceAll('_', ' ')} · {entity.workspace_label}</small>
        </button>
      </li>)}</ul>}
    </div>
  </section>
}
