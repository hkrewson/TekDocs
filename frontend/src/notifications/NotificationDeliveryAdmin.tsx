import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { formatDateTime, translate } from '../i18n/localization'
import { FilterMenu } from '../FilterMenu'

import type { NotificationDelivery, NotificationDeliveryAdminClient } from './api'

const states = ['', 'pending', 'processing', 'delivered', 'suppressed', 'dead_letter'] as const
type DeliveryStateFilter = typeof states[number]

function filterFrom(value: string | null): DeliveryStateFilter {
  return states.includes(value as DeliveryStateFilter) ? value as DeliveryStateFilter : ''
}

function stateLabel(state: string) {
  if (!state) return translate('notificationDelivery.allStatuses')
  return translate(`notificationDelivery.status.${state}` as 'notificationDelivery.status.pending' | 'notificationDelivery.status.processing' | 'notificationDelivery.status.delivered' | 'notificationDelivery.status.suppressed' | 'notificationDelivery.status.dead_letter')
}

export function NotificationDeliveryAdmin({ client }: { client: NotificationDeliveryAdminClient }) {
  const [parameters, setParameters] = useSearchParams()
  const filter = filterFrom(parameters.get('status'))
  const [revision, setRevision] = useState(0)
  const key = `${filter}\u0000${revision}`
  const [loaded, setLoaded] = useState<{ key: string; deliveries: NotificationDelivery[]; nextCursor: string | null } | null>(null)
  const [failureKey, setFailureKey] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [retrying, setRetrying] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [messageKind, setMessageKind] = useState<'success' | 'error'>('success')
  const visible = loaded?.key === key ? loaded : null
  const phase = failureKey === key ? 'error' : visible ? 'ready' : 'loading'

  function updateFilter(value: string) {
    const next = new URLSearchParams(parameters)
    if (value) next.set('status', value)
    else next.delete('status')
    setParameters(next)
    setMessage(null)
    setRetrying(null)
    setReason('')
  }

  useEffect(() => {
    let active = true
    void client.listDeliveries(filter || undefined).then((result) => {
      if (active) {
        setLoaded({ key, deliveries: result.results, nextCursor: result.next_cursor })
        setFailureKey(null)
      }
    }).catch(() => { if (active) setFailureKey(key) })
    return () => { active = false }
  }, [client, filter, key])

  async function loadOlder() {
    if (!visible?.nextCursor) return
    setLoadingMore(true)
    setMessage(null)
    try {
      const result = await client.listDeliveries(filter || undefined, visible.nextCursor)
      setLoaded({
        key,
        deliveries: [...visible.deliveries, ...result.results.filter((item) => !visible.deliveries.some((existing) => existing.id === item.id))],
        nextCursor: result.next_cursor,
      })
    } catch {
      setMessageKind('error')
      setMessage(translate('notificationDelivery.olderLoadFailed'))
    } finally {
      setLoadingMore(false)
    }
  }

  async function retry(delivery: NotificationDelivery) {
    setMessage(null)
    try {
      const updated = await client.retryDelivery(delivery.id, reason)
      setLoaded((current) => current?.key === key ? { ...current, deliveries: current.deliveries.map((item) => item.id === updated.id ? updated : item) } : current)
      setRetrying(null)
      setReason('')
      setMessageKind('success')
      setMessage(translate('notificationDelivery.retryQueued'))
    } catch {
      setMessageKind('error')
      setMessage(translate('notificationDelivery.retryFailed'))
    }
  }

  return <>
    <header className="page-header"><div><h1>{translate('notificationDelivery.heading')}</h1><p>{translate('notificationDelivery.intro')}</p></div></header>
    <section className="content-section notification-delivery-admin" aria-labelledby="notification-delivery-heading">
      <div className="section-heading"><h2 id="notification-delivery-heading">{translate('notificationDelivery.recent')}</h2><FilterMenu groups={[{ kind: 'choices', label: translate('notificationDelivery.status'), value: filter, choices: states.map((state) => ({ value: state, label: stateLabel(state) })), onChange: updateFilter }]} activeCount={filter ? 1 : 0} onClear={() => updateFilter('')} menuLabel={translate('notificationDelivery.filters')} /></div>
      <p className="workspace-area-note">{translate('notificationDelivery.privacyHelp')}</p>
      {filter && <div className="collection-active-filters"><button type="button" className="row-action" onClick={() => updateFilter('')}>{translate('notificationDelivery.status')}: {stateLabel(filter)} ×</button></div>}
      {message && <p className={messageKind === 'error' ? 'form-message error' : 'form-message success'} role={messageKind === 'error' ? 'alert' : 'status'}>{message}</p>}
      {phase === 'loading' && <p className="empty-state" role="status">{translate('notificationDelivery.loading')}</p>}
      {phase === 'error' && <div className="empty-state" role="alert"><p>{translate('notificationDelivery.loadFailed')}</p><button className="secondary-button" type="button" onClick={() => setRevision((value) => value + 1)}>{translate('common.retry')}</button></div>}
      {phase === 'ready' && visible?.deliveries.length === 0 && <p className="empty-state">{translate('notificationDelivery.empty')}</p>}
      {phase === 'ready' && visible && visible.deliveries.length > 0 && <ol className="plain-detail-list delivery-list">{visible.deliveries.map((delivery) => <li key={delivery.id}>
        <div><strong>{delivery.recipient}</strong><span>{delivery.organization || translate('notificationDelivery.noOrganization')}</span><span style={{ overflowWrap: 'anywhere' }}>{delivery.event_topic}</span></div>
        <div><strong>{stateLabel(delivery.state)}</strong><span>{translate('notificationDelivery.attemptSummary', { count: delivery.attempts })}</span><time dateTime={delivery.available_at}>{formatDateTime(delivery.available_at)}</time>
          {delivery.state === 'dead_letter' && (retrying === delivery.id
            ? <form className="delivery-retry" onSubmit={(event) => { event.preventDefault(); void retry(delivery) }}><label><span className="sr-only">{translate('notificationDelivery.retryReason')}</span><input autoFocus required minLength={3} maxLength={240} placeholder={translate('notificationDelivery.retryReasonPlaceholder')} value={reason} onChange={(event) => setReason(event.target.value)} /></label><button type="submit">{translate('common.retry')}</button><button type="button" onClick={() => { setRetrying(null); setReason('') }}>{translate('common.cancel')}</button></form>
            : <button className="row-action" type="button" onClick={() => setRetrying(delivery.id)}>{translate('common.retry')}</button>)}
        </div>
      </li>)}</ol>}
      {phase === 'ready' && visible?.nextCursor && <div className="portal-history-action"><button className="secondary-button" type="button" disabled={loadingMore} onClick={() => { void loadOlder() }}>{loadingMore ? translate('common.loading') : translate('notificationDelivery.loadOlder')}</button></div>}
    </section>
  </>
}
