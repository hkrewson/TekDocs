import { useEffect, useRef, useState } from 'react'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { DocumentOperationsChoice, DocumentRecord, DocumentScope, DocumentsClient } from './api'

function operationsFrom(document: DocumentRecord) {
  return { ownerId: document.owner_id ?? '', reviewDueOn: document.review_due_on ?? '', collection: document.collection ?? '', tags: (document.tags ?? []).join(', '), taxonomyTermIds: (document.taxonomy_terms ?? []).map((term) => term.id) }
}
function errorMessage(error: unknown) { return error instanceof Error ? error.message : translate('documentation.operationsWriteFailed') }

export function DocumentOperations({ document: selected, scope, client, onSaved, onClose }: { document: DocumentRecord; scope: DocumentScope; client: DocumentsClient; onSaved: (record: DocumentRecord) => void; onClose: () => void }) {
  const workspace = scope.organizationId
  const [operationsChoices, setOperationsChoices] = useState<DocumentOperationsChoice[]>([])
  const [operationsDraft, setOperationsDraft] = useState(() => operationsFrom(selected))
  const [taxonomyCatalog, setTaxonomyCatalog] = useState<Awaited<ReturnType<NonNullable<DocumentsClient['listTaxonomies']>>>['results']>([])
  const [taxonomyQuery, setTaxonomyQuery] = useState('')
  const [localTermDraft, setLocalTermDraft] = useState<{ taxonomyId: string; stableKey: string; label: string; description: string; aliases: string } | null>(null)
  const [reviewDraft, setReviewDraft] = useState({ reviewerId: '', note: '' })
  const [decisionDraft, setDecisionDraft] = useState({ decision: 'approved' as 'approved' | 'changes_requested', note: '' })

  const [baseline, setBaseline] = useState(() => operationsFrom(selected))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [retry, setRetry] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)
  const operationsDirty = JSON.stringify(operationsDraft) !== JSON.stringify(baseline)
  const dirty = operationsDirty || Boolean(reviewDraft.reviewerId || reviewDraft.note || decisionDraft.note || decisionDraft.decision !== 'approved' || localTermDraft)
  const attemptClose = useUnsavedChanges(dirty, saving)
  useEffect(() => { heading.current?.focus() }, [phase])
  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      client.operationsChoices ? client.operationsChoices(scope, controller.signal) : Promise.resolve([]),
      client.listTaxonomies ? client.listTaxonomies(scope, controller.signal) : Promise.resolve({ results: [] }),
    ]).then(([choices, catalog]) => {
      if (controller.signal.aborted) return
      setOperationsChoices(choices)
      setTaxonomyCatalog(catalog.results.filter((item) => item.binding === 'document_tags'))
      setPhase('ready')
    }).catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client, scope, retry])
  const saveOperations = async () => {
    if (saving || !client.updateOperations) return
    setSaving(true); setError(null); setMessage(null)
    try {
      const record = await client.updateOperations(scope, selected.id, {
        owner_id: operationsDraft.ownerId || null,
        review_due_on: operationsDraft.reviewDueOn || null,
        collection: operationsDraft.collection.trim(),
        tags: taxonomyCatalog.length > 0 ? [] : operationsDraft.tags.split(',').map((tag) => tag.trim()).filter(Boolean),
        taxonomy_term_ids: taxonomyCatalog.length > 0 ? operationsDraft.taxonomyTermIds : undefined,
      })
      setOperationsDraft(operationsFrom(record)); setBaseline(operationsFrom(record)); onSaved(record); setMessage(translate('documentation.operationsSaved'));
    } catch (operationsError) { setError(errorMessage(operationsError)) } finally { setSaving(false) }
  }
  const createLocalTerm = async () => {
    if (saving || !localTermDraft || !client.createLocalTaxonomyTerm || !workspace) return
    setSaving(true); setError(null); setMessage(null)
    try {
      const taxonomy = await client.createLocalTaxonomyTerm(scope, localTermDraft.taxonomyId, {
        stable_key: localTermDraft.stableKey.trim(),
        label: localTermDraft.label.trim(),
        description: localTermDraft.description.trim(),
        aliases: localTermDraft.aliases.split(',').map((value) => value.trim()).filter(Boolean),
      })
      setTaxonomyCatalog((current) => current.map((item) => item.id === taxonomy.id ? taxonomy : item))
      setLocalTermDraft(null)
      setMessage(translate('documentation.localTermCreated'))
    } catch (localTermError) { setError(errorMessage(localTermError)) } finally { setSaving(false) }
  }
  const requestReview = async () => {
    if (saving || !client.requestReview || !reviewDraft.reviewerId) return
    setSaving(true); setError(null); setMessage(null)
    try {
      const record = await client.requestReview(scope, selected.id, reviewDraft.reviewerId, reviewDraft.note)
      onSaved(record); setReviewDraft({ reviewerId: '', note: '' }); setMessage(translate('documentation.reviewRequested'));
    } catch (reviewError) { setError(errorMessage(reviewError)) } finally { setSaving(false) }
  }
  const decideReview = async () => {
    if (saving || !client.decideReview || !decisionDraft.note.trim()) return
    setSaving(true); setError(null); setMessage(null)
    try {
      const record = await client.decideReview(scope, selected.id, decisionDraft.decision, decisionDraft.note.trim())
      onSaved(record); setDecisionDraft({ decision: 'approved', note: '' }); setMessage(decisionDraft.decision === 'approved' ? translate('documentation.reviewApproved') : translate('documentation.changesRequested'));
    } catch (decisionError) { setError(errorMessage(decisionError)) } finally { setSaving(false) }
  }

  const summary = <dl className="document-review-summary">
    <div><dt>{translate('documentation.reviewStatus')}</dt><dd>{translate(`documentation.reviewState.${selected.review_state ?? 'unreviewed'}`)}</dd></div>
    <div><dt>{translate('documentation.owner')}</dt><dd>{selected.owner_name ?? translate('documentation.noOwner')}</dd></div>
    <div><dt>{translate('documentation.reviewDue')}</dt><dd>{selected.review_due_on ?? translate('documentation.notScheduled')}</dd></div>
    {selected.reviewer_name && <div><dt>{translate('documentation.reviewer')}</dt><dd>{selected.reviewer_name}</dd></div>}
    {selected.review_requested_at && <div><dt>{translate('documentation.reviewRequestedAt')}</dt><dd>{selected.review_requested_by_name} · {new Date(selected.review_requested_at).toLocaleString()}</dd></div>}
    {selected.review_decided_at && <div><dt>{translate('documentation.reviewDecidedAt')}</dt><dd>{new Date(selected.review_decided_at).toLocaleString()}</dd></div>}
    {selected.last_reviewed_at && <div><dt>{translate('documentation.lastApproved')}</dt><dd>{selected.last_reviewed_by_name} · {new Date(selected.last_reviewed_at).toLocaleString()}</dd></div>}
    {selected.review_note && <div><dt>{translate('documentation.latestReviewNote')}</dt><dd className="document-review-note">{selected.review_note}</dd></div>}
  </dl>
  return <section className="document-context-panel document-operations" aria-labelledby="document-operations-heading">
          <div className="section-heading"><div><h2 ref={heading} tabIndex={-1} id="document-operations-heading">{translate('documentation.ownershipAndReview')}</h2><p>{translate('documentation.healthSummary', { status: (selected.health_status ?? 'unreviewed').replaceAll('_', ' ') })}</p></div><button className="secondary-button" type="button" onClick={() => attemptClose(onClose)}>{translate('documentation.backToDocument')}</button></div>
          {summary}
          {error && <p role="alert">{error} {translate('documentation.operationsChoicesPreserved')}</p>}
          {message && <p role="status">{message}</p>}
          {phase === 'loading' && <p role="status">{translate('documentation.loadingOperations')}</p>}
          {phase === 'error' && <div role="alert"><p>{translate('documentation.operationsLoadFailed')}</p><button className="secondary-button" type="button" onClick={() => { setPhase('loading'); setRetry((value) => value + 1) }}>{translate('common.retry')}</button></div>}
          {phase === 'ready' && <>
          {operationsChoices.length === 0 && <p>{translate('documentation.noOwnersAvailable')}</p>}
          <fieldset className="document-operations-fields" disabled={saving}><legend>{translate('documentation.ownershipAndOrganization')}</legend>
          <div className="document-detail-fields">
            <label>{translate('documentation.owner')}<select value={operationsDraft.ownerId} onChange={(event) => setOperationsDraft({ ...operationsDraft, ownerId: event.target.value })}><option value="">{translate('documentation.noOwner')}</option>{operationsDraft.ownerId && !operationsChoices.some((choice) => choice.id === operationsDraft.ownerId) && <option value={operationsDraft.ownerId}>{selected.owner_name ?? translate('documentation.unavailableOwner')}</option>}{operationsChoices.map((choice) => <option key={choice.id} value={choice.id}>{choice.display_name}</option>)}</select></label>
            <label>{translate('documentation.reviewDue')}<input type="date" value={operationsDraft.reviewDueOn} onChange={(event) => setOperationsDraft({ ...operationsDraft, reviewDueOn: event.target.value })} /></label>
            <label>{translate('documentation.collection')}<input maxLength={120} value={operationsDraft.collection} onChange={(event) => setOperationsDraft({ ...operationsDraft, collection: event.target.value })} /></label>
            {taxonomyCatalog.length === 0 && <label>{translate('documentation.tags')}<input maxLength={400} value={operationsDraft.tags} onChange={(event) => setOperationsDraft({ ...operationsDraft, tags: event.target.value })} placeholder={translate('documentation.tagsPlaceholder')} /></label>}
          </div>
          {taxonomyCatalog.length > 0 && <fieldset className="document-taxonomy-picker"><legend>{translate('documentation.tags')}</legend><label className="taxonomy-search">{translate('documentation.searchTerms')}<input type="search" value={taxonomyQuery} onChange={(event) => setTaxonomyQuery(event.target.value)} placeholder={translate('documentation.searchTermsPlaceholder')} /></label>{(selected.taxonomy_terms ?? []).filter((selectedTerm) => operationsDraft.taxonomyTermIds.includes(selectedTerm.id) && !taxonomyCatalog.some((taxonomy) => taxonomy.current_version.terms.some((term) => term.id === selectedTerm.id))).map((selectedTerm) => <div className="taxonomy-choice-group" key={selectedTerm.id}><div className="section-heading"><div><strong>{selectedTerm.label}</strong><p>{translate('documentation.retainedTaxonomyTerm', { version: selectedTerm.taxonomy_version })}</p></div></div><div className="taxonomy-choice-list"><label><input type="checkbox" checked onChange={() => setOperationsDraft({ ...operationsDraft, taxonomyTermIds: operationsDraft.taxonomyTermIds.filter((id) => id !== selectedTerm.id) })} /><span>{selectedTerm.label}{selectedTerm.description && <small>{selectedTerm.description}</small>}</span></label></div></div>)}{taxonomyCatalog.map((taxonomy) => {
            const query = taxonomyQuery.trim().toLocaleLowerCase()
            const terms = taxonomy.current_version.terms.filter((term) => term.status === 'active' && (!query || operationsDraft.taxonomyTermIds.includes(term.id) || [term.stable_key, term.label, term.description, ...term.aliases].some((value) => value.toLocaleLowerCase().includes(query))))
            return <div className="taxonomy-choice-group" key={taxonomy.id}><div className="section-heading"><div><strong>{taxonomy.current_version.label}</strong>{taxonomy.current_version.description && <p>{taxonomy.current_version.description}</p>}</div>{workspace && taxonomy.current_version.allow_local_terms && client.createLocalTaxonomyTerm && <button className="row-action" type="button" onClick={() => setLocalTermDraft({ taxonomyId: taxonomy.id, stableKey: '', label: '', description: '', aliases: '' })}>{translate('documentation.addLocalTerm')}</button>}</div>{terms.length > 0 ? <div className="taxonomy-choice-list">{terms.map((term) => <label key={term.id}><input type="checkbox" checked={operationsDraft.taxonomyTermIds.includes(term.id)} onChange={(event) => setOperationsDraft({ ...operationsDraft, taxonomyTermIds: event.target.checked ? [...operationsDraft.taxonomyTermIds, term.id] : operationsDraft.taxonomyTermIds.filter((id) => id !== term.id) })} /><span>{term.label}{term.local && <small>{translate('documentation.clientLocalTerm')}</small>}{term.description && <small>{term.description}</small>}</span></label>)}</div> : <p>{translate('documentation.noMatchingTerms')}</p>}{localTermDraft?.taxonomyId === taxonomy.id && <div className="local-term-editor"><div className="document-detail-fields"><label>{translate('taxonomies.termKey')}<input maxLength={80} value={localTermDraft.stableKey} onChange={(event) => setLocalTermDraft({ ...localTermDraft, stableKey: event.target.value })} /></label><label>{translate('taxonomies.termLabel')}<input maxLength={120} value={localTermDraft.label} onChange={(event) => setLocalTermDraft({ ...localTermDraft, label: event.target.value })} /></label><label>{translate('taxonomies.termDescription')}<input maxLength={500} value={localTermDraft.description} onChange={(event) => setLocalTermDraft({ ...localTermDraft, description: event.target.value })} /></label><label>{translate('taxonomies.aliases')}<input maxLength={400} value={localTermDraft.aliases} onChange={(event) => setLocalTermDraft({ ...localTermDraft, aliases: event.target.value })} /></label></div><div className="document-actions"><button className="secondary-button" type="button" disabled={saving || !localTermDraft.stableKey.trim() || !localTermDraft.label.trim()} onClick={() => { void createLocalTerm() }}>{translate('documentation.createLocalTerm')}</button><button className="row-action" type="button" onClick={() => setLocalTermDraft(null)}>{translate('common.cancel')}</button></div></div>}</div>
          })}</fieldset>}
          <div className="document-actions"><button className="secondary-button" type="button" disabled={saving || !operationsDirty || Boolean(localTermDraft)} onClick={() => { void saveOperations() }}>{translate('documentation.saveOperations')}</button></div>
          </fieldset>
          {client.requestReview && <fieldset disabled={saving} className="document-review-form"><legend>{translate('documentation.requestReview')}</legend><p>{translate(selected.review_state === 'pending' ? 'documentation.replaceReviewHelp' : 'documentation.requestReviewHelp')}</p>{!operationsChoices.some((choice) => choice.can_approve) && <p>{translate('documentation.noReviewersAvailable')}</p>}<label>{translate('documentation.reviewer')}<select value={reviewDraft.reviewerId} onChange={(event) => setReviewDraft({ ...reviewDraft, reviewerId: event.target.value })}><option value="">{translate('documentation.chooseReviewer')}</option>{operationsChoices.filter((choice) => choice.can_approve).map((choice) => <option key={choice.id} value={choice.id}>{choice.display_name}</option>)}</select></label><label>{translate('documentation.reviewNote')}<textarea maxLength={500} value={reviewDraft.note} onChange={(event) => setReviewDraft({ ...reviewDraft, note: event.target.value })} /></label><button className="secondary-button" type="button" disabled={saving || !reviewDraft.reviewerId} onClick={() => { void requestReview() }}>{translate('documentation.sendForReview')}</button></fieldset>}
          {selected.review_state === 'pending' && client.decideReview && <fieldset disabled={saving} className="document-review-form"><legend>{translate('documentation.pendingReview')}</legend><p>{translate('documentation.assignedReviewerOnly')}</p><p>{translate('documentation.assignedReviewer', { reviewer: selected.reviewer_name ?? translate('documentation.unknownReviewer') })}</p><label>{translate('documentation.decision')}<select value={decisionDraft.decision} onChange={(event) => setDecisionDraft({ ...decisionDraft, decision: event.target.value as typeof decisionDraft.decision })}><option value="approved">{translate('documentation.approve')}</option><option value="changes_requested">{translate('documentation.requestChanges')}</option></select></label><label>{translate('documentation.decisionNote')}<textarea maxLength={500} required value={decisionDraft.note} onChange={(event) => setDecisionDraft({ ...decisionDraft, note: event.target.value })} /></label><button className="primary-button" type="button" disabled={saving || !decisionDraft.note.trim()} onClick={() => { void decideReview() }}>{translate('documentation.recordDecision')}</button></fieldset>}
          </>}
        </section>
}
