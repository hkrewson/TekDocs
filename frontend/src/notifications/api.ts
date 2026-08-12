import { browserCsrfToken } from '../auth/api'

export type NotificationTarget = {
  kind: 'organization_overview' | 'organization_documentation' | 'portal_documents' | 'portal_document'
  organization_id: string | null
  publication_id: string | null
}

export type InboxNotification = {
  id: string
  topic: string
  title: string
  message: string
  read: boolean
  created_at: string
  target: NotificationTarget | null
}

export type NotificationResult = {
  results: InboxNotification[]
  unread_count: number
  has_more: boolean
}

export interface NotificationsClient {
  list(): Promise<NotificationResult>
  setRead(id: string, read: boolean): Promise<InboxNotification>
}

async function decode<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(response.status === 403 ? 'Notification access was denied.' : 'Notifications could not be loaded.')
  return response.json() as Promise<T>
}

export function createBrowserNotificationsClient(portal = false): NotificationsClient {
  const base = portal ? '/api/v1/portal/notifications' : '/api/v1/notifications'
  return {
    async list() {
      return decode(await fetch(base, { credentials: 'same-origin', headers: { Accept: 'application/json' } }))
    },
    async setRead(id, read) {
      const token = browserCsrfToken()
      if (!token) throw new Error('The browser security token is unavailable. Refresh and try again.')
      return decode(await fetch(`${base}/${id}`, {
        method: 'PATCH',
        credentials: 'same-origin',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': token },
        body: JSON.stringify({ read }),
      }))
    },
  }
}

export const browserNotificationsClient = createBrowserNotificationsClient()
export const browserPortalNotificationsClient = createBrowserNotificationsClient(true)
