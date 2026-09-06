import { useEffect, useState } from 'react'
import { Check, Copy, Plus, RefreshCw } from 'lucide-react'
import { translate } from '../i18n/localization'

import { CollectionPagination } from '../CollectionPagination'
import { FilterMenu } from '../FilterMenu'
import type { WorkspaceContext } from '../workspaces/api'
import type { IssuedWebhookEndpoint, WebhookDelivery, WebhookDraft, WebhookEndpoint, WebhooksClient } from './api'

const OUTBOUND_TOPICS = ['client_invitation.issued', 'client_invitation.accepted', 'document_publication.available', 'document_publication.withdrawn']
const EMPTY_DRAFT: WebhookDraft = { name: '', direction: 'outbound', url: '', topics: [OUTBOUND_TOPICS[0]] }

export function Webhooks({ workspace, client, embedded = false }: { workspace: WorkspaceContext; client: WebhooksClient; embedded?: boolean }) {
  const [endpoints, setEndpoints] = useState<WebhookEndpoint[]>([])
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([])
  const [draft, setDraft] = useState<WebhookDraft>(EMPTY_DRAFT)
  const [showForm, setShowForm] = useState(false)
  const [issued, setIssued] = useState<IssuedWebhookEndpoint | null>(null)
  const [copied, setCopied] = useState(false)
  const [stateFilter, setStateFilter] = useState('')
  const [page, setPage] = useState(1)
  const [pageState, setPageState] = useState({ count: 0, pageSize: 25, hasMore: false })
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pendingRotate, setPendingRotate] = useState<WebhookEndpoint | null>(null)
  const [retrying, setRetrying] = useState<WebhookDelivery | null>(null)
  const [retryReason, setRetryReason] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([client.listEndpoints(workspace, controller.signal), client.listDeliveries(workspace, page, stateFilter, controller.signal)])
      .then(([nextEndpoints, result]) => { setEndpoints(nextEndpoints); setDeliveries(result.results); setPageState({ count: result.count, pageSize: result.page_size, hasMore: result.has_more }); setPhase('ready') })
      .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client, page, stateFilter, workspace])

  async function create() {
    setSaving(true); setError(null)
    try {
      const next = await client.createEndpoint(workspace, draft)
      setIssued(next); setEndpoints((current) => [...current, next].sort((a, b) => a.name.localeCompare(b.name)))
      setDraft(EMPTY_DRAFT); setShowForm(false)
    } catch { setError(translate('webhooks.createFailed')) } finally { setSaving(false) }
  }

  async function changeActive(endpoint: WebhookEndpoint) {
    setSaving(true); setError(null)
    try { const next = await client.setActive(workspace, endpoint, !endpoint.active); setEndpoints((current) => current.map((item) => item.id === next.id ? next : item)) }
    catch { setError(translate('webhooks.changeFailed')) }
    finally { setSaving(false) }
  }

  async function rotate(endpoint: WebhookEndpoint) {
    setSaving(true); setError(null)
    try { const next = await client.rotate(workspace, endpoint); setIssued(next); setEndpoints((current) => current.map((item) => item.id === next.id ? next : item)); setPendingRotate(null) }
    catch { setError(translate('webhooks.rotateFailed')) }
    finally { setSaving(false) }
  }

  async function retry(delivery: WebhookDelivery) {
    const reason = retryReason.trim()
    if (!reason) return
    setSaving(true); setError(null)
    try { const next = await client.retry(workspace, delivery, reason); setDeliveries((current) => current.map((item) => item.id === next.id ? next : item)); setRetrying(null); setRetryReason('') }
    catch { setError(translate('webhooks.retryFailed')) }
    finally { setSaving(false) }
  }

  return <>
    {embedded
      ? <div className="section-heading"><div><h2>Webhooks</h2><p>{translate('webhooks.intro')}</p></div><button className="primary-button" type="button" onClick={() => setShowForm((value) => !value)}><Plus size={16} />{translate('integrations.newEndpoint')}</button></div>
      : <header className="page-header"><div><h1>Webhooks</h1></div><button className="primary-button" type="button" aria-label={translate('webhooks.new')} title={translate('webhooks.new')} onClick={() => setShowForm((value) => !value)}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('webhooks.new')}</span></button></header>}
    {error && <div className="form-message error" role="alert">{error}</div>}
    {issued && <section className="content-section webhook-secret" aria-labelledby="webhook-secret-title"><div><h2 id="webhook-secret-title">{translate('webhooks.secretHeading')}</h2><p>{translate('webhooks.secretHelp')}</p></div><code>{issued.signing_secret}</code><button className="secondary-button" type="button" onClick={() => { void navigator.clipboard.writeText(issued.signing_secret); setCopied(true) }}>{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? 'Copied' : 'Copy secret'}</button><button className="secondary-button" type="button" onClick={() => { setIssued(null); setCopied(false) }}>{translate('integrations.iSavedIt')}</button></section>}
    {showForm && <section className="content-section" aria-labelledby="new-webhook-title"><div className="section-heading"><div><h2 id="new-webhook-title">New endpoint</h2><p>{translate('webhooks.setupHelp')}</p></div></div><div className="form-grid"><label><span>Name</span><input value={draft.name} maxLength={100} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label><label><span>Direction</span><select value={draft.direction} onChange={(event) => { const direction = event.target.value as WebhookDraft['direction']; setDraft({ ...draft, direction, url: direction === 'inbound' ? '' : draft.url, topics: direction === 'inbound' ? ['integration.ping'] : [OUTBOUND_TOPICS[0]] }) }}><option value="outbound">Outbound</option><option value="inbound">Inbound</option></select></label>{draft.direction === 'outbound' && <label className="wide-field"><span>HTTPS destination</span><input type="url" value={draft.url} placeholder="https://hooks.example.com/tekdocs" onChange={(event) => setDraft({ ...draft, url: event.target.value })} /><small>{translate('webhooks.destinationHelp')}</small></label>}<label className="wide-field"><span>Event topic</span><select value={draft.topics[0]} onChange={(event) => setDraft({ ...draft, topics: [event.target.value] })}>{(draft.direction === 'inbound' ? ['integration.ping'] : OUTBOUND_TOPICS).map((topic) => <option key={topic}>{topic}</option>)}</select></label></div><div className="form-actions"><button className="primary-button" type="button" disabled={saving || !draft.name || (draft.direction === 'outbound' && !draft.url)} onClick={() => { void create() }}>{saving ? 'Creating…' : 'Create endpoint'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setShowForm(false)}>{translate('common.cancel')}</button></div></section>}
    <section className="content-section" aria-busy={phase === 'loading'}><div className="section-heading"><div><h2>Endpoints</h2><p>See where events are sent and whether each endpoint is available.</p></div></div>{phase === 'loading' && <p className="empty-state" role="status">Loading webhooks…</p>}{phase === 'error' && <p className="empty-state" role="alert">{translate('webhooks.loadFailed')}</p>}{phase === 'ready' && endpoints.length === 0 && <p className="empty-state">No webhook endpoints belong to this organization.</p>}{phase === 'ready' && endpoints.length > 0 && <div className="table-scroll" role="group" aria-label={translate('webhooks.endpointTable')} tabIndex={0}><table><thead><tr><th>Name</th><th>Direction</th><th>Destination</th><th>Topics</th><th>Status</th><th>Actions</th></tr></thead><tbody>{endpoints.map((endpoint) => <tr key={endpoint.id}><td><strong>{endpoint.name}</strong><br /><small>Key {endpoint.secret_prefix}… · generation {endpoint.secret_generation}</small></td><td>{endpoint.direction}</td><td><code>{endpoint.inbound_path ?? endpoint.url}</code></td><td>{endpoint.topics.join(', ')}</td><td>{endpoint.active ? 'Active' : 'Inactive'}</td><td><div className="table-actions"><button className="secondary-button" type="button" disabled={saving} onClick={() => { void changeActive(endpoint) }}>{endpoint.active ? 'Deactivate' : 'Activate'}</button><button className="icon-button" type="button" disabled={saving} aria-label={`Replace the signing secret for ${endpoint.name}`} title={`Replace the signing secret for ${endpoint.name}`} onClick={() => setPendingRotate(endpoint)}><RefreshCw size={15} /></button></div></td></tr>)}</tbody></table></div>}{pendingRotate && <div className="archive-confirmation" role="alertdialog" aria-labelledby="rotate-webhook-heading" aria-describedby="rotate-webhook-help"><div><strong id="rotate-webhook-heading">{translate('webhooks.rotateHeading', { name: pendingRotate.name })}</strong><p id="rotate-webhook-help">{translate('webhooks.rotateHelp')}</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void rotate(pendingRotate) }}>{translate('webhooks.rotateAction')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setPendingRotate(null)}>{translate('common.cancel')}</button></div></div>}</section>
    <section className="content-section"><div className="section-heading"><div><h2>Outbound deliveries</h2><p>See whether each event arrived and retry failed deliveries when needed.</p></div><FilterMenu groups={[{ kind: 'choices', label: 'Status', value: stateFilter, choices: [{ value: '', label: 'All statuses' }, { value: 'pending', label: 'Waiting' }, { value: 'processing', label: 'Sending' }, { value: 'delivered', label: 'Delivered' }, { value: 'dead_letter', label: 'Failed' }], onChange: (value) => { setStateFilter(value); setPage(1) } }]} activeCount={stateFilter ? 1 : 0} onClear={() => { setStateFilter(''); setPage(1) }} menuLabel="Delivery filters" /></div>{phase === 'ready' && deliveries.length === 0 ? <p className="empty-state">No outbound deliveries match this filter.</p> : <div className="table-scroll" role="group" aria-label={translate('webhooks.deliveryTable')} tabIndex={0}><table><thead><tr><th>Created</th><th>Endpoint</th><th>Topic</th><th>Status</th><th>Attempts</th><th>Result</th><th>Action</th></tr></thead><tbody>{deliveries.map((delivery) => <tr key={delivery.id}><td>{new Date(delivery.created_at).toLocaleString()}</td><td>{delivery.endpoint_name}</td><td>{delivery.topic}</td><td>{delivery.state === 'dead_letter' ? 'Failed' : delivery.state === 'processing' ? 'Sending' : delivery.state === 'pending' ? 'Waiting' : 'Delivered'}</td><td>{delivery.attempts}</td><td>{delivery.response_status ?? (delivery.last_error_code || '—')}</td><td>{delivery.state === 'dead_letter' && <button className="secondary-button" type="button" disabled={saving} onClick={() => { setRetrying(delivery); setRetryReason('') }}>{translate('common.retry')}</button>}</td></tr>)}</tbody></table></div>}{retrying && <div className="archive-confirmation" role="alertdialog" aria-labelledby="retry-webhook-heading" aria-describedby="retry-webhook-help"><div><strong id="retry-webhook-heading">{translate('webhooks.retryHeading', { name: retrying.endpoint_name })}</strong><p id="retry-webhook-help">{translate('webhooks.retryHelp')}</p><label><span>{translate('webhooks.retryReason')}</span><input value={retryReason} maxLength={240} onChange={(event) => setRetryReason(event.target.value)} /></label></div><div className="form-actions"><button className="primary-button" type="button" disabled={saving || !retryReason.trim()} onClick={() => { void retry(retrying) }}>{translate('webhooks.retryAction')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => { setRetrying(null); setRetryReason('') }}>{translate('common.cancel')}</button></div></div>}<CollectionPagination label="Webhook deliveries" page={page} pageSize={pageState.pageSize} count={pageState.count} hasMore={pageState.hasMore} onPageChange={setPage} /></section>
  </>
}
