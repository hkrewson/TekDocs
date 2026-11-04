import { useEffect, useMemo, useState } from 'react'
import { translate } from '../i18n/localization'
import { DocumentRemoteSourcePanel, type DocumentRemoteSourceDraft } from './DocumentRemoteSourcePanel'
import type { DocumentRemoteObservation, DocumentRemoteSource } from './api'
import type { RepositoryClient } from './repositoryApi'

const emptyDraft: DocumentRemoteSourceDraft = {
  url: '', source_kind: 'auto', enabled: true, check_interval_minutes: 1440,
}

export function RepositoryRemoteSource({ contentId, organizationId, client, disabled, onEditingChange }: {
  contentId: string
  organizationId?: string
  client: RepositoryClient
  disabled: boolean
  onEditingChange: (editing: boolean) => void
}) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [source, setSource] = useState<DocumentRemoteSource | null>(null)
  const [draft, setDraft] = useState<DocumentRemoteSourceDraft>(emptyDraft)
  const [observations, setObservations] = useState<DocumentRemoteObservation[]>([])
  const [error, setError] = useState('')
  const dirty = useMemo(() => source === null
    ? draft.url !== ''
    : draft.url !== source.url || draft.source_kind !== source.source_kind
      || draft.enabled !== source.enabled || draft.check_interval_minutes !== source.check_interval_minutes,
  [draft, source])

  useEffect(() => onEditingChange(dirty), [dirty, onEditingChange])
  useEffect(() => () => onEditingChange(false), [onEditingChange])

  async function load() {
    setBusy(true); setError('')
    try {
      const current = await client.remoteSource(contentId, organizationId)
      setSource(current ?? null)
      setDraft(current ?? emptyDraft)
      setObservations(current ? (await client.remoteObservations(contentId, organizationId)).results : [])
      setOpen(true)
    } catch { setError(translate('documentation.sourceReviewUnavailable')) }
    finally { setBusy(false) }
  }

  async function save() {
    setBusy(true); setError('')
    try {
      const saved = await client.saveRemoteSource(contentId, draft, organizationId)
      setSource(saved); setDraft(saved)
      setObservations((await client.remoteObservations(contentId, organizationId)).results)
    } catch { setError(translate('documentation.sourceReviewUnavailable')) }
    finally { setBusy(false) }
  }

  async function check() {
    setBusy(true); setError('')
    try {
      await client.checkRemoteSource(contentId, organizationId)
      setObservations((await client.remoteObservations(contentId, organizationId)).results)
    } catch { setError(translate('documentation.sourceReviewUnavailable')) }
    finally { setBusy(false) }
  }

  async function apply(observation: DocumentRemoteObservation) {
    if (!observation.apply_review?.fingerprint) return
    setBusy(true); setError('')
    try {
      await client.applyRemoteObservation(contentId, observation.id, observation.apply_review.fingerprint, organizationId)
      const current = await client.remoteSource(contentId, organizationId)
      setSource(current ?? null); setDraft(current ?? emptyDraft)
      setObservations((await client.remoteObservations(contentId, organizationId)).results)
    } catch { setError(translate('documentation.sourceReviewUnavailable')) }
    finally { setBusy(false) }
  }

  if (!open) return <div className="document-actions">
    <button type="button" className="secondary-button" disabled={disabled || busy} onClick={() => { void load() }}>
      {translate('documentation.webSource')}
    </button>
    {error && <p role="alert" className="form-message error">{error}</p>}
  </div>
  return <>
    {error && <p role="alert" className="form-message error">{error}</p>}
    <DocumentRemoteSourcePanel
      busy={busy} settingsDirty={dirty} source={source} draft={draft} observations={observations}
      onApplyObservation={(item) => { void apply(item) }} onCheck={() => { void check() }}
      onClose={() => { if (!dirty) setOpen(false) }} onDraftChange={setDraft} onSave={() => { void save() }}
    />
  </>
}
