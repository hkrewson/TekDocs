import { useEffect, useState } from 'react'
import { formatDateTime, translate} from '../i18n/localization'

import type { NotificationDelivery, NotificationDeliveryAdminClient } from './api'

const states = ['', 'pending', 'processing', 'delivered', 'suppressed', 'dead_letter']

export function NotificationDeliveryAdmin({ client }: { client: NotificationDeliveryAdminClient }) {
  const [deliveries, setDeliveries] = useState<NotificationDelivery[]>([])
  const [filter, setFilter] = useState('')
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [retrying, setRetrying] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    client.listDeliveries(filter || undefined).then((result) => {
      if (active) { setDeliveries(result.results); setNextCursor(result.next_cursor); setPhase('ready') }
    }).catch(() => { if (active) setPhase('error') })
    return () => { active = false }
  }, [client, filter])

  async function loadOlder() {
    if (!nextCursor) return
    setLoadingMore(true)
    try {
      const result = await client.listDeliveries(filter || undefined, nextCursor)
      setDeliveries((current) => [...current, ...result.results.filter((item) => !current.some((existing) => existing.id === item.id))])
      setNextCursor(result.next_cursor)
    } catch {
      setMessage('Older delivery metadata could not be loaded.')
    } finally {
      setLoadingMore(false)
    }
  }

  async function retry(delivery: NotificationDelivery) {
    setMessage(null)
    try {
      const updated = await client.retryDelivery(delivery.id, reason)
      setDeliveries((items) => items.map((item) => item.id === updated.id ? updated : item))
      setRetrying(null)
      setReason('')
      setMessage('Delivery returned to the queue.')
    } catch {
      setMessage('The delivery could not be retried. Refresh and verify that it is still dead-lettered.')
    }
  }

  return <>
    <header className="page-header"><div><h1>Email delivery</h1></div></header>
    <section className="content-section notification-delivery-admin">
      <div className="section-heading"><h2>Recent deliveries</h2><label>State <select value={filter} onChange={(event) => { setPhase('loading'); setFilter(event.target.value) }}>{states.map((state) => <option key={state} value={state}>{state ? state.replace('_', ' ') : 'All states'}</option>)}</select></label></div>
      <p className="workspace-area-note">Message content and recipient email addresses are intentionally excluded from this view.</p>
      {message && <p role="status">{message}</p>}
      {phase === 'loading' && <p role="status">Loading delivery metadata…</p>}
      {phase === 'error' && <p role="alert">Delivery metadata could not be loaded.</p>}
      {phase === 'ready' && deliveries.length === 0 && <p>No deliveries match this state.</p>}
      {phase === 'ready' && deliveries.length > 0 && <div className="table-scroll"><table><thead><tr><th>Recipient</th><th>Organization</th><th>Event</th><th>State</th><th>Attempts</th><th>Available</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{deliveries.map((delivery) => <tr key={delivery.id}><td>{delivery.recipient}</td><td>{delivery.organization}</td><td>{delivery.event_topic}</td><td>{delivery.state.replace('_', ' ')}</td><td>{delivery.attempts}</td><td><time dateTime={delivery.available_at}>{formatDateTime(delivery.available_at)}</time></td><td>{delivery.state === 'dead_letter' && (retrying === delivery.id ? <form className="delivery-retry" onSubmit={(event) => { event.preventDefault(); void retry(delivery) }}><label><span className="sr-only">Retry reason</span><input autoFocus required minLength={3} maxLength={240} placeholder="Reason for retry" value={reason} onChange={(event) => setReason(event.target.value)} /></label><button type="submit">{translate('common.retry')}</button><button type="button" onClick={() => { setRetrying(null); setReason('') }}>{translate('common.cancel')}</button></form> : <button type="button" onClick={() => setRetrying(delivery.id)}>{translate('common.retry')}</button>)}</td></tr>)}</tbody></table></div>}
      {phase === 'ready' && nextCursor && <div className="portal-history-action"><button className="secondary-button" type="button" disabled={loadingMore} onClick={() => { void loadOlder() }}>{loadingMore ? 'Loading…' : 'Load older deliveries'}</button></div>}
    </section>
  </>
}
