import { afterEach, describe, expect, it, vi } from 'vitest'

import { createBrowserNotificationsClient } from './api'

afterEach(() => vi.restoreAllMocks())

describe('notifications API', () => {
  it('uses isolated portal routes and CSRF-protects state changes', async () => {
    document.cookie = 'csrftoken=notification-csrf; path=/'
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ results: [], unread_count: 0, has_more: false }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: 'notification-1', topic: 'document_publication.available', title: 'Published', message: 'Available', read: true,
        created_at: '2026-08-12T01:00:00Z', target: null,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ email_enabled: true, invitation_events: true, publication_events: true }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ email_enabled: false, invitation_events: true, publication_events: true }), { status: 200 }))
    const client = createBrowserNotificationsClient(true)

    await client.list()
    await client.setRead('notification-1', true)
    await client.getPreferences()
    await client.updatePreferences({ email_enabled: false, invitation_events: true, publication_events: true })

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/portal/notifications')
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/portal/notifications/notification-1')
    expect(fetchMock.mock.calls[1]?.[1]?.headers).toEqual(expect.objectContaining({ 'X-CSRFToken': 'notification-csrf' }))
    expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/v1/portal/notification-preferences')
    expect(fetchMock.mock.calls[3]?.[0]).toBe('/api/v1/portal/notification-preferences')
    expect(fetchMock.mock.calls[3]?.[1]?.headers).toEqual(expect.objectContaining({ 'X-CSRFToken': 'notification-csrf' }))
  })
})
