import { useEffect, useState } from 'react'
import { formatDateTime, translate } from '../i18n/localization'
import { FilterMenu } from '../FilterMenu'

import type { NotificationDelivery, NotificationDeliveryAdminClient } from './api'

const states = ['', 'pending', 'processing', 'delivered', 'suppressed', 'dead_letter']

function stateLabel(state: string) {
  if (!state) return translate('notificationDelivery.allStatuses')
  return translate(`notificationDelivery.status.${state}` as 'notificationDelivery.status.pending' | 'notificationDelivery.status.processing' | 'notificationDelivery.status.delivered' | 'notificationDelivery.status.suppressed' | 'notificationDelivery.status.dead_letter')
}

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
      setMessage(translate('notificationDelivery.olderLoadFailed'))
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
      setMessage(translate('notificationDelivery.retryQueued'))
    } catch {
      setMessage(translate('notificationDelivery.retryFailed'))
    }
  }

  return <>
    <header className="page-header"><div><h1>{translate('notificationDelivery.heading')}</h1></div></header>
    <section className="content-section notification-delivery-admin">
      <div className="section-heading"><h2>{translate('notificationDelivery.recent')}</h2><FilterMenu groups={[{ kind: 'choices', label: translate('notificationDelivery.status'), value: filter, choices: states.map((state) => ({ value: state, label: stateLabel(state) })), onChange: (value) => { setPhase('loading'); setFilter(value) } }]} activeCount={filter ? 1 : 0} onClear={() => { setPhase('loading'); setFilter('') }} menuLabel={translate('notificationDelivery.filters')} /></div>
      <p className="workspace-area-note">{translate('notificationDelivery.privacyHelp')}</p>
      {message && <p role="status">{message}</p>}
      {phase === 'loading' && <p role="status">{translate('notificationDelivery.loading')}</p>}
      {phase === 'error' && <p role="alert">{translate('notificationDelivery.loadFailed')}</p>}
      {phase === 'ready' && deliveries.length === 0 && <p>{translate('notificationDelivery.empty')}</p>}
      {phase === 'ready' && deliveries.length > 0 && <div className="table-scroll" role="group" aria-label={translate('notifications.deliveryTable')} tabIndex={0}><table><thead><tr><th>{translate('notificationDelivery.recipient')}</th><th>{translate('notificationDelivery.organization')}</th><th>{translate('notificationDelivery.event')}</th><th>{translate('notificationDelivery.status')}</th><th>{translate('notificationDelivery.attempts')}</th><th>{translate('notificationDelivery.nextAttempt')}</th><th><span className="sr-only">{translate('notificationDelivery.actions')}</span></th></tr></thead><tbody>{deliveries.map((delivery) => <tr key={delivery.id}><td>{delivery.recipient}</td><td>{delivery.organization}</td><td>{delivery.event_topic}</td><td>{stateLabel(delivery.state)}</td><td>{delivery.attempts}</td><td><time dateTime={delivery.available_at}>{formatDateTime(delivery.available_at)}</time></td><td>{delivery.state === 'dead_letter' && (retrying === delivery.id ? <form className="delivery-retry" onSubmit={(event) => { event.preventDefault(); void retry(delivery) }}><label><span className="sr-only">{translate('notificationDelivery.retryReason')}</span><input autoFocus required minLength={3} maxLength={240} placeholder={translate('notificationDelivery.retryReasonPlaceholder')} value={reason} onChange={(event) => setReason(event.target.value)} /></label><button type="submit">{translate('common.retry')}</button><button type="button" onClick={() => { setRetrying(null); setReason('') }}>{translate('common.cancel')}</button></form> : <button type="button" onClick={() => setRetrying(delivery.id)}>{translate('common.retry')}</button>)}</td></tr>)}</tbody></table></div>}
      {phase === 'ready' && nextCursor && <div className="portal-history-action"><button className="secondary-button" type="button" disabled={loadingMore} onClick={() => { void loadOlder() }}>{loadingMore ? translate('common.loading') : translate('notificationDelivery.loadOlder')}</button></div>}
    </section>
  </>
}
