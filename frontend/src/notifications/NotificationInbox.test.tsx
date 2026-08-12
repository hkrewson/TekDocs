import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { NotificationInbox } from './NotificationInbox'
import type { NotificationsClient } from './api'

const notification = {
  id: 'notification-1',
  topic: 'document_publication.available',
  title: 'Documentation published',
  message: 'Access guide is now available.',
  read: false,
  created_at: '2026-08-12T01:00:00Z',
  target: { kind: 'portal_document' as const, organization_id: null, publication_id: 'publication-1' },
}

describe('NotificationInbox', () => {
  it('loads on demand, exposes unread state, and marks an activated item read', async () => {
    const setRead = vi.fn().mockResolvedValue({ ...notification, read: true })
    const client = {
      list: vi.fn().mockResolvedValue({ results: [notification], unread_count: 1, has_more: false }),
      setRead,
    } satisfies NotificationsClient
    const onOpen = vi.fn()
    const user = userEvent.setup()
    render(<NotificationInbox client={client} onOpen={onOpen} />)

    expect(client.list).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Notifications' }))
    expect(await screen.findByText('Access guide is now available.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Notifications, 1 unread' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Access guide is now available/i }))
    expect(setRead).toHaveBeenCalledWith('notification-1', true)
    expect(onOpen).toHaveBeenCalledWith(notification.target)
  })

  it('supports an empty state and retry after a bounded load failure', async () => {
    const client = {
      list: vi.fn()
        .mockRejectedValueOnce(new Error('Notifications could not be loaded.'))
        .mockResolvedValueOnce({ results: [], unread_count: 0, has_more: false }),
      setRead: vi.fn(),
    } as unknown as NotificationsClient
    const user = userEvent.setup()
    render(<NotificationInbox client={client} onOpen={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Notifications' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Notifications could not be loaded.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('No notifications yet.')).toBeInTheDocument()
  })
})
