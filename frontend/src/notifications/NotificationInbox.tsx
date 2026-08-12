import { Bell, Check, Mail } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import type { InboxNotification, NotificationsClient, NotificationTarget } from './api'

export function NotificationInbox({ client, onOpen }: {
  client: NotificationsClient
  onOpen: (target: NotificationTarget) => void | Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [notifications, setNotifications] = useState<InboxNotification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [phase, setPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  async function load() {
    setPhase('loading')
    setError(null)
    try {
      const result = await client.list()
      setNotifications(result.results)
      setUnreadCount(result.unread_count)
      setPhase('ready')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Notifications could not be loaded.')
      setPhase('error')
    }
  }

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false) }
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  function toggleOpen() {
    const next = !open
    setOpen(next)
    if (next) void load()
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
      <button className="notification-trigger" type="button" aria-label={unreadCount ? `Notifications, ${unreadCount} unread` : 'Notifications'} aria-expanded={open} onClick={toggleOpen}>
        <Bell size={19} aria-hidden="true" />
        {unreadCount > 0 && <span className="notification-count" aria-hidden="true">{unreadCount > 99 ? '99+' : unreadCount}</span>}
      </button>
      {open && <section className="notification-popover" aria-label="Notifications">
        <header><h2>Notifications</h2>{phase === 'ready' && <span>{unreadCount} unread</span>}</header>
        {phase === 'loading' && <p className="notification-state" role="status">Loading notifications…</p>}
        {phase === 'error' && <div className="notification-state" role="alert"><p>{error}</p><button type="button" onClick={() => { void load() }}>Try again</button></div>}
        {phase === 'ready' && notifications.length === 0 && <p className="notification-state">No notifications yet.</p>}
        {phase === 'ready' && notifications.length > 0 && <ul className="notification-list">{notifications.map((notification) => <li key={notification.id} className={notification.read ? '' : 'unread'}>
          <button className="notification-content" type="button" disabled={!notification.target} onClick={() => { void activate(notification) }}>
            <strong>{notification.title}</strong>
            <span>{notification.message}</span>
            <time dateTime={notification.created_at}>{new Date(notification.created_at).toLocaleString()}</time>
          </button>
          <button className="notification-read-toggle" type="button" aria-label={notification.read ? `Mark ${notification.title} unread` : `Mark ${notification.title} read`} onClick={() => { void setRead(notification, !notification.read) }}>
            {notification.read ? <Mail size={15} aria-hidden="true" /> : <Check size={15} aria-hidden="true" />}
          </button>
        </li>)}</ul>}
      </section>}
    </div>
  )
}
