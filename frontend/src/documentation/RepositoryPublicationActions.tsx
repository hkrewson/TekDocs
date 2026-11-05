import { useEffect, useRef, useState } from 'react'
import { formatDateTime, translate, type MessageId } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import { RepositoryRecentAuthenticationRequiredError, type RepositoryClient, type RepositoryEvidence, type RepositoryPublicationAction, type RepositoryWorkflow } from './repositoryApi'

const labels: Record<RepositoryPublicationAction, MessageId> = {
  accept_review: 'repository.lifecycle.acceptReview', reject_review: 'repository.lifecycle.rejectReview',
  create_package: 'repository.lifecycle.createPackage', authorize_package: 'repository.lifecycle.authorizePackage',
  reject_package: 'repository.lifecycle.rejectPackage', create_static: 'repository.lifecycle.createStatic',
  release_client: 'repository.lifecycle.releaseClient', withdraw_client: 'repository.lifecycle.withdraw',
  authorize_delivery: 'repository.lifecycle.deliver', release_internal: 'repository.lifecycle.publish',
  withdraw_internal: 'repository.lifecycle.withdraw',
}

const stageLabels: Record<string, MessageId> = {
  review: 'repository.lifecycle.reviewStage', package: 'repository.lifecycle.packageStage',
  authorization: 'repository.lifecycle.authorizationStage', publication: 'repository.lifecycle.publicationStage',
  release: 'repository.lifecycle.releaseStage', internal: 'repository.lifecycle.internalStage',
}
const stateLabels: Record<string, MessageId> = {
  recorded: 'repository.lifecycle.recorded', released: 'repository.lifecycle.published',
  superseded: 'repository.lifecycle.superseded', withdrawn: 'repository.lifecycle.withdrawn', rejected: 'repository.lifecycle.rejected',
}

export function RepositoryPublicationActions({ contentId, organizationId, commit, canRetain, selected, client, onCreated, onChanged, onEditingChange }: {
  contentId: string; organizationId?: string; commit: string | null; canRetain: boolean
  selected: RepositoryEvidence | null; client: RepositoryClient
  onCreated: (record: RepositoryEvidence) => void; onChanged: () => void
  onEditingChange: (editing: boolean) => void
}) {
  const [creating, setCreating] = useState(false)
  const [audience, setAudience] = useState('msp_internal')
  const [reviewedCommit, setReviewedCommit] = useState<string | null>(null)
  const [workflow, setWorkflow] = useState<RepositoryWorkflow | null>(null)
  const [loading, setLoading] = useState(selected !== null)
  const [reload, setReload] = useState(0)
  const [action, setAction] = useState<RepositoryPublicationAction | null>(null)
  const [reason, setReason] = useState('')
  const [replace, setReplace] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [loadError, setLoadError] = useState(false)
  const [authenticationRequired, setAuthenticationRequired] = useState(false)
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const request = useRef<AbortController | null>(null)
  useUnsavedChanges(creating || action !== null, busy, () => { setCreating(false); setAction(null); setReason(''); setReplace(false) }, creating || action !== null)
  useEffect(() => () => request.current?.abort(), [])
  useEffect(() => { onEditingChange(creating || action !== null || busy) }, [creating, action, busy, onEditingChange])
  const evidenceId = selected?.id
  const evidenceCommit = selected?.source_commit
  useEffect(() => {
    if (!evidenceId) return
    const controller = new AbortController()
    void client.publicationWorkflow(evidenceId, organizationId, controller.signal)
      .then(result => {
        if (controller.signal.aborted) return
        if (result.evidence_id !== evidenceId || result.source_commit !== evidenceCommit) throw new Error('Publication identity changed')
        setWorkflow(result)
      })
      .catch(() => { if (!controller.signal.aborted) { setWorkflow(null); setLoadError(true) } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [client, evidenceId, evidenceCommit, organizationId, reload])

  async function retain() {
    if (busy || !canRetain || !reviewedCommit || reviewedCommit !== commit) return
    const controller = new AbortController(); request.current = controller
    setBusy(true); setError('')
    try {
      const record = await client.createEvidence(contentId, audience, reviewedCommit, organizationId, controller.signal)
      if (controller.signal.aborted) return
      setCreating(false); onCreated(record)
    } catch { if (!controller.signal.aborted) setError(translate('repository.lifecycle.retainFailed')) }
    finally { if (!controller.signal.aborted) setBusy(false) }
  }

  const release = action === 'release_internal' || action === 'release_client'
  const replacement = release && !!workflow?.active_publication_id && workflow.active_publication_id !== workflow.publication_id
  const needsReason = action !== 'create_package' && action !== 'create_static'
  async function decide() {
    if (!selected || !workflow || !action || busy || loading || authenticationRequired || !workflow.actions.includes(action)
      || (needsReason && !reason.trim()) || (replacement && !replace)) return
    const controller = new AbortController(); request.current = controller
    setBusy(true); setError('')
    try {
      await client.publicationAction(selected.id, action, reason.trim(), replacement ? workflow.active_publication_id : null, organizationId, controller.signal)
      if (controller.signal.aborted) return
      setAction(null); setReason(''); setReplace(false); setMessage(''); setWorkflow(null); setLoading(true); setLoadError(false); setReload(value => value + 1); onChanged()
    } catch (caught) {
      if (!controller.signal.aborted) {
        setAuthenticationRequired(caught instanceof RepositoryRecentAuthenticationRequiredError)
        setError(translate(caught instanceof RepositoryRecentAuthenticationRequiredError ? 'repository.lifecycle.authenticationRequired' : 'repository.lifecycle.decisionFailed'))
      }
    }
    finally { if (!controller.signal.aborted) setBusy(false) }
  }

  async function confirmPassword() {
    if (!authenticationRequired || !password || busy) return
    const controller = new AbortController(); request.current = controller
    const submitted = password; setPassword(''); setBusy(true); setError(''); setMessage('')
    try {
      await client.reauthenticate(submitted)
      if (!controller.signal.aborted) { setAuthenticationRequired(false); setMessage(translate('repository.lifecycle.passwordConfirmed')) }
    } catch { if (!controller.signal.aborted) setError(translate('repository.lifecycle.passwordFailed')) }
    finally { if (!controller.signal.aborted) setBusy(false) }
  }

  async function download() {
    if (!selected || !workflow?.verified || !workflow.publication_id || busy) return
    const controller = new AbortController(); request.current = controller
    setBusy(true); setError('')
    try {
      const file = workflow.audience === 'msp_internal'
        ? await client.internalPublicationPdf(selected.id, workflow.content_digest, organizationId, controller.signal)
        : await client.exportStatic(selected.id, 'pdf', workflow.content_digest, organizationId, controller.signal)
      if (controller.signal.aborted) return
      const url = URL.createObjectURL(file.content)
      const link = document.createElement('a'); link.href = url; link.download = file.name; link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch { if (!controller.signal.aborted) setError(translate('repository.lifecycle.downloadFailed')) }
    finally { if (!controller.signal.aborted) setBusy(false) }
  }

  return <section aria-label={translate('repository.lifecycle.heading')}>
    <h3>{translate('repository.lifecycle.heading')}</h3>
    {!creating && <button type="button" className="primary-button" disabled={busy || !canRetain || action !== null} onClick={() => { setReviewedCommit(commit); setCreating(true); setError('') }}>{translate('repository.lifecycle.publishDocument')}</button>}
    {!canRetain && <p>{translate('repository.lifecycle.saveFirst')}</p>}
    {creating && <form aria-label={translate('repository.lifecycle.publishDocument')} onSubmit={event => { event.preventDefault(); void retain() }}>
      <label>{translate('repository.lifecycle.audience')}<select disabled={busy} value={audience} onChange={event => setAudience(event.target.value)}><option value="msp_internal">{translate('repository.audienceInternal')}</option>{organizationId && <option value="client_visible">{translate('repository.audienceClient')}</option>}</select></label>
      <p>{translate(audience === 'client_visible' ? 'repository.lifecycle.clientNotice' : 'repository.lifecycle.internalNotice')}</p>
      <div className="form-actions"><button className="primary-button" disabled={busy || !canRetain || reviewedCommit !== commit}>{translate('repository.lifecycle.retain')}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => setCreating(false)}>{translate('common.cancel')}</button></div>
    </form>}
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {authenticationRequired && <form aria-label={translate('repository.lifecycle.confirmPassword')} onSubmit={event => { event.preventDefault(); void confirmPassword() }}>
      <label>{translate('auth.currentPassword')}<input type="password" autoComplete="current-password" required value={password} disabled={busy} onChange={event => setPassword(event.target.value)} /></label>
      <button className="secondary-button" disabled={busy || !password}>{translate('repository.lifecycle.confirmPassword')}</button>
    </form>}
    {selected && <div>
      {loading && <p role="status">{translate('repository.lifecycle.loading')}</p>}
      {loadError && <p role="alert">{translate('repository.lifecycle.loadFailed')}</p>}
      <button type="button" className="secondary-button" disabled={busy || loading} onClick={() => { setReplace(false); setLoading(true); setLoadError(false); setReload(value => value + 1) }}>{translate('repository.lifecycle.refresh')}</button>
      {workflow && !loading && <>
        <p role="status">{translate(stateLabels[workflow.state] ?? 'repository.lifecycle.recorded')}</p>
        {!workflow.verified && <p role="alert">{translate('repository.lifecycle.integrityFailed')}</p>}
        {workflow.state === 'recorded' && <p>{translate(stageLabels[workflow.stage] ?? 'repository.lifecycle.reviewStage')}</p>}
        {workflow.audience === 'client_visible' && <p>{translate(workflow.delivery_effective ? 'repository.lifecycle.clientReady' : 'repository.lifecycle.clientUnavailable')}</p>}
        {workflow.actions.length === 0 && workflow.state === 'recorded' && <p>{translate('repository.lifecycle.otherReviewer')}</p>}
        {!creating && !action && <div className="form-actions">{workflow.actions.map(value => <button key={value} type="button" className="secondary-button" disabled={busy} onClick={() => { setAction(value); setReason(''); setReplace(false); setError('') }}>{translate(labels[value])}</button>)}</div>}
        {action && <form aria-label={translate(labels[action])} onSubmit={event => { event.preventDefault(); void decide() }}>
          {needsReason && <label>{translate('repository.lifecycle.reason')}<textarea maxLength={500} required value={reason} disabled={busy} onChange={event => setReason(event.target.value)} /></label>}
          {replacement && <label><input type="checkbox" checked={replace} disabled={busy} onChange={event => setReplace(event.target.checked)} />{translate('repository.lifecycle.replace')}</label>}
          <div className="form-actions"><button className="primary-button" disabled={busy || authenticationRequired || !workflow.actions.includes(action) || (needsReason && !reason.trim()) || (replacement && !replace)}>{translate('repository.lifecycle.confirm')}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => { setAction(null); setReason(''); setReplace(false); setAuthenticationRequired(false); setPassword(''); setMessage('') }}>{translate('common.cancel')}</button></div>
        </form>}
        {workflow.publication_id && <button type="button" className="secondary-button" disabled={busy || !workflow.verified} onClick={() => { void download() }}>{translate('repository.lifecycle.download')}</button>}
        {workflow.events.length > 0 && <ol>{workflow.events.map(event => <li key={event.id}>{translate(event.action === 'withdrawn' ? 'repository.lifecycle.withdrawn' : 'repository.lifecycle.published')} · <time dateTime={event.occurred_at}>{formatDateTime(event.occurred_at)}</time> · {event.reason}</li>)}</ol>}
      </>}
    </div>}
  </section>
}
