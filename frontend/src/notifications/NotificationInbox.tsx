import { Bell, Check, Mail, X } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { formatDateTime, formatHour, runtimeTimeZone, translate } from '../i18n/localization'

import type { InboxNotification, NotificationPreferences, NotificationsClient, NotificationTarget } from './api'

const UnsavedChangesDialog = lazy(() => import('../navigation/UnsavedChangesDialog'))

const defaultPreferences: NotificationPreferences = {
  email_enabled: true,
  invitation_events: true,
  publication_events: true,
  delivery_mode: 'immediate',
  timezone: runtimeTimeZone(),
  quiet_start: null,
  quiet_end: null,
  daily_digest_hour: 8,
}

export function NotificationInbox({ client, onOpen }: {
  client: NotificationsClient
  onOpen: (target: NotificationTarget) => void | Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [notifications, setNotifications] = useState<InboxNotification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [phase, setPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [view, setView] = useState<'inbox' | 'preferences'>('inbox')
  const [preferences, setPreferences] = useState(defaultPreferences)
  const [savedPreferences, setSavedPreferences] = useState(defaultPreferences)
  const [preferencesPhase, setPreferencesPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [savingPreferences, setSavingPreferences] = useState(false)
  const [preferencesMessage, setPreferencesMessage] = useState<string | null>(null)
  const [discardTarget, setDiscardTarget] = useState<'close' | 'inbox' | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const preferencesDirty = preferencesPhase === 'ready' && JSON.stringify(preferences) !== JSON.stringify(savedPreferences)

  async function load(cursor?: string) {
    if (cursor) setLoadingMore(true)
    else setPhase('loading')
    setError(null)
    setActionError(null)
    try {
      const result = await client.list(cursor)
      setNotifications((current) => cursor
        ? [...current, ...result.results.filter((item) => !current.some((existing) => existing.id === item.id))]
        : result.results)
      if (!cursor) setUnreadCount(result.unread_count)
      setNextCursor(result.next_cursor ?? null)
      setPhase('ready')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : translate('notifications.loadFailed'))
      setPhase('error')
    } finally {
      setLoadingMore(false)
    }
  }

  async function loadPreferences() {
    setView('preferences')
    setPreferencesPhase('loading')
    setPreferencesMessage(null)
    setActionError(null)
    try {
      const loadedPreferences = await client.getPreferences()
      setPreferences(loadedPreferences)
      setSavedPreferences(loadedPreferences)
      setPreferencesPhase('ready')
    } catch {
      setPreferencesPhase('error')
    }
  }

  async function savePreferences() {
    setSavingPreferences(true)
    setPreferencesMessage(null)
    try {
      const updated = await client.updatePreferences(preferences)
      setPreferences(updated)
      setSavedPreferences(updated)
      setPreferencesMessage(translate('notifications.preferencesSaved'))
    } catch {
      setPreferencesMessage(translate('notifications.preferencesSaveFailed'))
    } finally {
      setSavingPreferences(false)
    }
  }

  const finishDeparture = useCallback((target: 'close' | 'inbox') => {
    setDiscardTarget(null)
    if (target === 'inbox') {
      setPreferences(savedPreferences)
      setPreferencesMessage(null)
      setView('inbox')
      return
    }
    setOpen(false)
    triggerRef.current?.focus()
  }, [savedPreferences])

  const requestDeparture = useCallback((target: 'close' | 'inbox') => {
    if (preferencesDirty || savingPreferences) setDiscardTarget(target)
    else finishDeparture(target)
  }, [finishDeparture, preferencesDirty, savingPreferences])

  useEffect(() => {
    if (!open) return
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const close = (event: MouseEvent) => { if (!ref.current?.contains(event.target as Node)) requestDeparture('close') }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !discardTarget) requestDeparture('close')
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', escape)
    return () => {
      document.body.style.overflow = overflow
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', escape)
    }
  }, [discardTarget, open, requestDeparture])

  useEffect(() => {
    if (open) headingRef.current?.focus()
  }, [open, view])

  function toggleOpen() {
    if (open) {
      requestDeparture('close')
      return
    }
    setOpen(true)
    setView('inbox')
    void load()
  }

  async function setRead(notification: InboxNotification, read: boolean) {
    setActionError(null)
    try {
      const updated = await client.setRead(notification.id, read)
      setNotifications((items) => items.map((item) => item.id === updated.id ? updated : item))
      setUnreadCount((count) => Math.max(0, count + (read ? -1 : 1)))
    } catch {
      setActionError(translate('notifications.updateFailed'))
    }
  }

  async function activate(notification: InboxNotification) {
    if (!notification.read) await setRead(notification, true)
    if (notification.target) {
      setOpen(false)
      await onOpen(notification.target)
    }
  }

  return (
    <div className="notification-menu" ref={ref}>
      <button ref={triggerRef} className="notification-trigger" type="button" aria-label={unreadCount ? translate('notifications.triggerUnread', { count: unreadCount }) : translate('notifications.trigger')} aria-controls="notification-popover" aria-expanded={open} onClick={toggleOpen}>
        <Bell size={19} aria-hidden="true" />
        {unreadCount > 0 && <span className="notification-count" aria-hidden="true">{unreadCount > 99 ? '99+' : unreadCount}</span>}
      </button>
      {open && <section id="notification-popover" className="notification-popover" role="dialog" aria-modal="true" aria-labelledby="notification-popover-heading" aria-busy={phase === 'loading' || loadingMore}>
        <header><h2 id="notification-popover-heading" ref={headingRef} tabIndex={-1}>{view === 'inbox' ? translate('notifications.heading') : translate('notifications.emailPreferences')}</h2>{view === 'inbox' && phase === 'ready' && <span>{translate('notifications.unread', { count: unreadCount })}</span>}<button className="icon-button notification-close" type="button" aria-label={translate('notifications.close')} onClick={() => requestDeparture('close')}><X size={18} aria-hidden="true" /></button></header>
        <div className="notification-popover-body">
          {view === 'inbox' && <>
            <div className="notification-toolbar"><button type="button" onClick={() => { void loadPreferences() }}>{translate('notifications.emailPreferences')}</button></div>
            {actionError && <p className="notification-state" role="alert">{actionError}</p>}
            {phase === 'loading' && <p className="notification-state" role="status">{translate('notifications.loading')}</p>}
            {phase === 'error' && <div className="notification-state" role="alert"><p>{error}</p><button type="button" onClick={() => { void load() }}>{translate('notifications.tryAgain')}</button></div>}
            {phase === 'ready' && notifications.length === 0 && <p className="notification-state">{translate('notifications.empty')}</p>}
            {phase === 'ready' && notifications.length > 0 && <ul className="notification-list">{notifications.map((notification) => <li key={notification.id} className={notification.read ? '' : 'unread'}>
              <button className="notification-content" type="button" disabled={!notification.target} onClick={() => { void activate(notification) }}>
                <strong>{notification.title}</strong>
                <span>{notification.message}</span>
                <time dateTime={notification.created_at}>{formatDateTime(notification.created_at)}</time>
              </button>
              <button className="notification-read-toggle" type="button" aria-label={notification.read ? translate('notifications.markUnread', { title: notification.title }) : translate('notifications.markRead', { title: notification.title })} onClick={() => { void setRead(notification, !notification.read) }}>
                {notification.read ? <Mail size={15} aria-hidden="true" /> : <Check size={15} aria-hidden="true" />}
              </button>
            </li>)}</ul>}
            {phase === 'ready' && nextCursor && <div className="notification-history-action"><button type="button" disabled={loadingMore} onClick={() => { void load(nextCursor) }}>{loadingMore ? translate('notifications.loadingOlder') : translate('notifications.loadOlder')}</button></div>}
          </>}
          {view === 'preferences' && <>
            <div className="notification-toolbar"><button type="button" onClick={() => requestDeparture('inbox')}>{translate('notifications.backToNotifications')}</button></div>
            {preferencesPhase === 'loading' && <p className="notification-state" role="status">{translate('notifications.preferencesLoading')}</p>}
            {preferencesPhase === 'error' && <div className="notification-state" role="alert"><p>{translate('notifications.preferencesLoadFailed')}</p><button type="button" onClick={() => { void loadPreferences() }}>{translate('notifications.tryAgain')}</button></div>}
            {preferencesPhase === 'ready' && <form className="notification-preferences" onSubmit={(event) => { event.preventDefault(); void savePreferences() }}>
              <label><input type="checkbox" checked={preferences.email_enabled} onChange={(event) => setPreferences((current) => ({ ...current, email_enabled: event.target.checked }))} />{translate('notifications.sendEmail')}</label>
              <label><input type="checkbox" disabled={!preferences.email_enabled} checked={preferences.invitation_events} onChange={(event) => setPreferences((current) => ({ ...current, invitation_events: event.target.checked }))} />{translate('notifications.invitationEvents')}</label>
              <label><input type="checkbox" disabled={!preferences.email_enabled} checked={preferences.publication_events} onChange={(event) => setPreferences((current) => ({ ...current, publication_events: event.target.checked }))} />{translate('notifications.publicationEvents')}</label>
              <label className="notification-field"><span>{translate('notifications.deliverySchedule')}</span><select disabled={!preferences.email_enabled} value={preferences.delivery_mode} onChange={(event) => setPreferences((current) => ({ ...current, delivery_mode: event.target.value as NotificationPreferences['delivery_mode'] }))}><option value="immediate">{translate('notifications.deliveryImmediate')}</option><option value="hourly">{translate('notifications.deliveryHourly')}</option><option value="daily">{translate('notifications.deliveryDaily')}</option></select></label>
              <label className="notification-field"><span>{translate('notifications.timezone')}</span><input type="text" disabled={!preferences.email_enabled} value={preferences.timezone} onChange={(event) => setPreferences((current) => ({ ...current, timezone: event.target.value }))} /></label>
              {preferences.delivery_mode === 'daily' && <label className="notification-field"><span>{translate('notifications.dailyHour')}</span><select disabled={!preferences.email_enabled} value={preferences.daily_digest_hour} onChange={(event) => setPreferences((current) => ({ ...current, daily_digest_hour: Number(event.target.value) }))}>{Array.from({ length: 24 }, (_, hour) => <option key={hour} value={hour}>{formatHour(hour)}</option>)}</select></label>}
              <label><input type="checkbox" disabled={!preferences.email_enabled} checked={preferences.quiet_start !== null} onChange={(event) => setPreferences((current) => ({ ...current, quiet_start: event.target.checked ? '22:00' : null, quiet_end: event.target.checked ? '07:00' : null }))} />{translate('notifications.quietHours')}</label>
              {preferences.quiet_start !== null && <div className="notification-quiet-hours"><label><span>{translate('notifications.quietStarts')}</span><input type="time" value={preferences.quiet_start} onChange={(event) => setPreferences((current) => ({ ...current, quiet_start: event.target.value }))} /></label><label><span>{translate('notifications.quietEnds')}</span><input type="time" value={preferences.quiet_end ?? '07:00'} onChange={(event) => setPreferences((current) => ({ ...current, quiet_end: event.target.value }))} /></label></div>}
              <p>{translate('notifications.alwaysDelivered')}</p>
              <div><button type="submit" disabled={savingPreferences}>{savingPreferences ? translate('notifications.saving') : translate('notifications.savePreferences')}</button>{preferencesMessage && <span role="status">{preferencesMessage}</span>}</div>
            </form>}
          </>}
        </div>
        {discardTarget && <Suspense fallback={null}><UnsavedChangesDialog dirty={preferencesDirty} busy={savingPreferences} onKeep={() => setDiscardTarget(null)} onDiscard={() => finishDeparture(discardTarget)} /></Suspense>}
      </section>}
    </div>
  )
}
