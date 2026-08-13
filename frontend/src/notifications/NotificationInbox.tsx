import { Bell, Check, Mail } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { formatDateTime, formatHour, runtimeTimeZone } from '../i18n/localization'

import type { InboxNotification, NotificationPreferences, NotificationsClient, NotificationTarget } from './api'

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
  const [view, setView] = useState<'inbox' | 'preferences'>('inbox')
  const [preferences, setPreferences] = useState(defaultPreferences)
  const [preferencesPhase, setPreferencesPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [savingPreferences, setSavingPreferences] = useState(false)
  const [preferencesMessage, setPreferencesMessage] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)

  async function load(cursor?: string) {
    if (cursor) setLoadingMore(true)
    else setPhase('loading')
    setError(null)
    try {
      const result = await client.list(cursor)
      setNotifications((current) => cursor
        ? [...current, ...result.results.filter((item) => !current.some((existing) => existing.id === item.id))]
        : result.results)
      if (!cursor) setUnreadCount(result.unread_count)
      setNextCursor(result.next_cursor ?? null)
      setPhase('ready')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Notifications could not be loaded.')
      setPhase('error')
    } finally {
      setLoadingMore(false)
    }
  }

  async function loadPreferences() {
    setView('preferences')
    setPreferencesPhase('loading')
    setPreferencesMessage(null)
    try {
      setPreferences(await client.getPreferences())
      setPreferencesPhase('ready')
    } catch {
      setPreferencesPhase('error')
    }
  }

  async function savePreferences() {
    setSavingPreferences(true)
    setPreferencesMessage(null)
    try {
      setPreferences(await client.updatePreferences(preferences))
      setPreferencesMessage('Email preferences saved.')
    } catch {
      setPreferencesMessage('Email preferences could not be saved.')
    } finally {
      setSavingPreferences(false)
    }
  }

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false) }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  useEffect(() => {
    if (open) headingRef.current?.focus()
  }, [open, view])

  function toggleOpen() {
    const next = !open
    setOpen(next)
    if (next) {
      setView('inbox')
      void load()
    }
  }

  async function setRead(notification: InboxNotification, read: boolean) {
    try {
      const updated = await client.setRead(notification.id, read)
      setNotifications((items) => items.map((item) => item.id === updated.id ? updated : item))
      setUnreadCount((count) => Math.max(0, count + (read ? -1 : 1)))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The notification could not be updated.')
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
      <button ref={triggerRef} className="notification-trigger" type="button" aria-label={unreadCount ? `Notifications, ${unreadCount} unread` : 'Notifications'} aria-controls="notification-popover" aria-expanded={open} onClick={toggleOpen}>
        <Bell size={19} aria-hidden="true" />
        {unreadCount > 0 && <span className="notification-count" aria-hidden="true">{unreadCount > 99 ? '99+' : unreadCount}</span>}
      </button>
      {open && <section id="notification-popover" className="notification-popover" role="dialog" aria-labelledby="notification-popover-heading" aria-busy={phase === 'loading' || loadingMore}>
        <header><h2 id="notification-popover-heading" ref={headingRef} tabIndex={-1}>{view === 'inbox' ? 'Notifications' : 'Email preferences'}</h2>{view === 'inbox' && phase === 'ready' && <span>{unreadCount} unread</span>}</header>
        {view === 'inbox' && <>
          <div className="notification-toolbar"><button type="button" onClick={() => { void loadPreferences() }}>Email preferences</button></div>
          {phase === 'loading' && <p className="notification-state" role="status">Loading notifications…</p>}
          {phase === 'error' && <div className="notification-state" role="alert"><p>{error}</p><button type="button" onClick={() => { void load() }}>Try again</button></div>}
          {phase === 'ready' && notifications.length === 0 && <p className="notification-state">No notifications yet.</p>}
          {phase === 'ready' && notifications.length > 0 && <ul className="notification-list">{notifications.map((notification) => <li key={notification.id} className={notification.read ? '' : 'unread'}>
          <button className="notification-content" type="button" disabled={!notification.target} onClick={() => { void activate(notification) }}>
            <strong>{notification.title}</strong>
            <span>{notification.message}</span>
            <time dateTime={notification.created_at}>{formatDateTime(notification.created_at)}</time>
          </button>
          <button className="notification-read-toggle" type="button" aria-label={notification.read ? `Mark ${notification.title} unread` : `Mark ${notification.title} read`} onClick={() => { void setRead(notification, !notification.read) }}>
            {notification.read ? <Mail size={15} aria-hidden="true" /> : <Check size={15} aria-hidden="true" />}
          </button>
          </li>)}</ul>}
          {phase === 'ready' && nextCursor && <div className="notification-history-action"><button type="button" disabled={loadingMore} onClick={() => { void load(nextCursor) }}>{loadingMore ? 'Loading…' : 'Load older notifications'}</button></div>}
        </>}
        {view === 'preferences' && <>
          <div className="notification-toolbar"><button type="button" onClick={() => setView('inbox')}>Back to notifications</button></div>
          {preferencesPhase === 'loading' && <p className="notification-state" role="status">Loading email preferences…</p>}
          {preferencesPhase === 'error' && <div className="notification-state" role="alert"><p>Email preferences could not be loaded.</p><button type="button" onClick={() => { void loadPreferences() }}>Try again</button></div>}
          {preferencesPhase === 'ready' && <form className="notification-preferences" onSubmit={(event) => { event.preventDefault(); void savePreferences() }}>
            <label><input type="checkbox" checked={preferences.email_enabled} onChange={(event) => setPreferences((current) => ({ ...current, email_enabled: event.target.checked }))} />Send notification email</label>
            <label><input type="checkbox" disabled={!preferences.email_enabled} checked={preferences.invitation_events} onChange={(event) => setPreferences((current) => ({ ...current, invitation_events: event.target.checked }))} />Client invitation activity</label>
            <label><input type="checkbox" disabled={!preferences.email_enabled} checked={preferences.publication_events} onChange={(event) => setPreferences((current) => ({ ...current, publication_events: event.target.checked }))} />Published documentation</label>
            <label className="notification-field"><span>Delivery schedule</span><select disabled={!preferences.email_enabled} value={preferences.delivery_mode} onChange={(event) => setPreferences((current) => ({ ...current, delivery_mode: event.target.value as NotificationPreferences['delivery_mode'] }))}><option value="immediate">As notifications occur</option><option value="hourly">Hourly digest</option><option value="daily">Daily digest</option></select></label>
            <label className="notification-field"><span>Time zone</span><input type="text" disabled={!preferences.email_enabled} value={preferences.timezone} onChange={(event) => setPreferences((current) => ({ ...current, timezone: event.target.value }))} /></label>
            {preferences.delivery_mode === 'daily' && <label className="notification-field"><span>Daily delivery hour</span><select disabled={!preferences.email_enabled} value={preferences.daily_digest_hour} onChange={(event) => setPreferences((current) => ({ ...current, daily_digest_hour: Number(event.target.value) }))}>{Array.from({ length: 24 }, (_, hour) => <option key={hour} value={hour}>{formatHour(hour)}</option>)}</select></label>}
            <label><input type="checkbox" disabled={!preferences.email_enabled} checked={preferences.quiet_start !== null} onChange={(event) => setPreferences((current) => ({ ...current, quiet_start: event.target.checked ? '22:00' : null, quiet_end: event.target.checked ? '07:00' : null }))} />Use quiet hours</label>
            {preferences.quiet_start !== null && <div className="notification-quiet-hours"><label><span>Starts</span><input type="time" value={preferences.quiet_start} onChange={(event) => setPreferences((current) => ({ ...current, quiet_start: event.target.value }))} /></label><label><span>Ends</span><input type="time" value={preferences.quiet_end ?? '07:00'} onChange={(event) => setPreferences((current) => ({ ...current, quiet_end: event.target.value }))} /></label></div>}
            <p>Account-security and invitation-link email is always delivered separately.</p>
            <div><button type="submit" disabled={savingPreferences}>{savingPreferences ? 'Saving…' : 'Save preferences'}</button>{preferencesMessage && <span role="status">{preferencesMessage}</span>}</div>
          </form>}
        </>}
      </section>}
    </div>
  )
}
