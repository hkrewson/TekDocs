import { RefreshCw, X } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { DocumentRemoteObservation, DocumentRemoteSource } from './api'

export type DocumentRemoteSourceDraft = Pick<DocumentRemoteSource, 'url' | 'source_kind' | 'enabled' | 'check_interval_minutes'>

type DocumentRemoteSourcePanelProps = {
  busy: boolean
  draft: DocumentRemoteSourceDraft
  observations: DocumentRemoteObservation[]
  source: DocumentRemoteSource | null
  onApplyObservation: (observation: DocumentRemoteObservation) => void
  onCheck: () => void
  onClose: () => void
  onDraftChange: (draft: DocumentRemoteSourceDraft) => void
  onSave: () => void
}

export function DocumentRemoteSourcePanel({
  busy,
  draft,
  observations,
  source,
  onApplyObservation,
  onCheck,
  onClose,
  onDraftChange,
  onSave,
}: DocumentRemoteSourcePanelProps) {
  return <section className="document-context-panel remote-source" aria-labelledby="remote-source-heading">
    <div className="section-heading">
      <div>
        <h2 id="remote-source-heading">{translate('documentation.webSource')}</h2>
        <p>{translate('documentation.webSourceHelp')}</p>
      </div>
      <button className="icon-button" type="button" aria-label={translate('documentation.closeWebSource')} onClick={onClose}><X size={16} /></button>
    </div>
    <label>
      {translate('documentation.publicUrl')}
      <input type="url" value={draft.url} onChange={(event) => onDraftChange({ ...draft, url: event.target.value })} placeholder="https://example.com/document" />
    </label>
    <div className="new-block-fields">
      <label>
        {translate('documentation.sourceFormat')}
        <select value={draft.source_kind} onChange={(event) => onDraftChange({ ...draft, source_kind: event.target.value as DocumentRemoteSourceDraft['source_kind'] })}>
          <option value="auto">{translate('documentation.detectAutomatically')}</option>
          <option value="markdown">Markdown</option>
          <option value="html">HTML</option>
        </select>
      </label>
      <label>
        {translate('documentation.checkInterval')}
        <input type="number" min="15" max="10080" value={draft.check_interval_minutes} onChange={(event) => onDraftChange({ ...draft, check_interval_minutes: Number(event.target.value) })} />
      </label>
    </div>
    <label className="checkbox-field">
      <input type="checkbox" checked={draft.enabled} onChange={(event) => onDraftChange({ ...draft, enabled: event.target.checked })} />
      {translate('documentation.scheduledChecks')}
    </label>
    <div className="document-actions">
      <button className="primary-button" type="button" disabled={busy || !draft.url} onClick={onSave}>{translate('documentation.saveSource')}</button>
      {source && <button className="secondary-button" type="button" onClick={onCheck}><RefreshCw size={15} />{translate('documentation.checkNow')}</button>}
    </div>
    {observations.length > 0 && <ol className="remote-observations">{observations.map((observation) => <li key={observation.id}>
      <header>
        <strong>{observation.state === 'changed' ? translate('documentation.changeDetected') : observation.state === 'failed' ? translate('documentation.checkFailed') : translate('documentation.noChange')}</strong>
        <span>{new Date(observation.fetched_at).toLocaleString()}</span>
      </header>
      {observation.diff && <pre>{observation.diff}</pre>}
      {observation.state === 'changed' && observation.id !== source?.last_applied_observation_id && <button className="secondary-button" type="button" onClick={() => onApplyObservation(observation)}>{translate('documentation.applyReviewedChange')}</button>}
    </li>)}</ol>}
  </section>
}
