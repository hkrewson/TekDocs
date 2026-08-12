import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { NotificationDeliveryAdmin } from './NotificationDeliveryAdmin'
import type { NotificationDeliveryAdminClient } from './api'

const delivery = {
  id: 'delivery-1', state: 'dead_letter' as const, surface: 'client_portal', attempts: 1,
  retry_generation: 0, event_topic: 'document_publication.available', organization: 'Example Client',
  recipient: 'Client Reader', created_at: '2026-08-12T01:00:00Z', available_at: '2026-08-12T01:00:30Z',
  last_attempt_at: '2026-08-12T01:00:00Z', delivered_at: null, last_error_code: 'recipient_rejected',
}

describe('NotificationDeliveryAdmin', () => {
  it('lists metadata without content and requires a reason to retry dead letters', async () => {
    const retryDelivery = vi.fn().mockResolvedValue({ ...delivery, state: 'pending', attempts: 0, retry_generation: 1 })
    const client = { listDeliveries: vi.fn().mockResolvedValue({ results: [delivery], has_more: false, next_cursor: null }), retryDelivery } satisfies NotificationDeliveryAdminClient
    const user = userEvent.setup()
    render(<NotificationDeliveryAdmin client={client} />)

    expect(await screen.findByText('Client Reader')).toBeInTheDocument()
    expect(screen.queryByText(/document body/i)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await user.type(screen.getByPlaceholderText('Reason for retry'), 'SMTP service recovered')
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(retryDelivery).toHaveBeenCalledWith('delivery-1', 'SMTP service recovered')
    expect(await screen.findByText('Delivery returned to the queue.')).toBeInTheDocument()
  })

  it('appends an older delivery page without losing the visible history', async () => {
    const older = { ...delivery, id: 'delivery-2', recipient: 'Older Reader', state: 'delivered' as const }
    const listDeliveries = vi.fn()
      .mockResolvedValueOnce({ results: [delivery], has_more: true, next_cursor: 'older-page' })
      .mockResolvedValueOnce({ results: [older], has_more: false, next_cursor: null })
    const client = {
      listDeliveries,
      retryDelivery: vi.fn(),
    } satisfies NotificationDeliveryAdminClient
    const user = userEvent.setup()
    render(<NotificationDeliveryAdmin client={client} />)

    expect(await screen.findByText('Client Reader')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Load older deliveries' }))

    expect(await screen.findByText('Older Reader')).toBeInTheDocument()
    expect(screen.getByText('Client Reader')).toBeInTheDocument()
    expect(listDeliveries).toHaveBeenNthCalledWith(2, undefined, 'older-page')
    expect(screen.queryByRole('button', { name: 'Load older deliveries' })).not.toBeInTheDocument()
  })
})
