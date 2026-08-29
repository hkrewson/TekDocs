import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'

import type { OperationsClient } from './api'
import { ActivityLog } from './ActivityLog'

it('shows value-minimized activity and applies bounded filters', async () => {
  const activity = vi.fn().mockResolvedValue({
    results: [{ id: 'event-1', action: 'document.review_requested', actor_id: 'user-1', actor_name: 'Alex Rivera', entity_id: 'doc-1', entity_name: 'Recovery runbook', entity_type: 'document', request_id: 'request-1', occurred_at: '2026-08-28T15:00:00Z' }],
    count: 1, page: 1, page_size: 50, has_more: false, actions: ['document.review_requested'],
  })
  const client = { activity, reminders: vi.fn(), createReminder: vi.fn(), reminderCalendarUrl: vi.fn() } satisfies OperationsClient
  const user = userEvent.setup()

  render(<ActivityLog workspace={null} client={client} />)
  expect(await screen.findByText('Recovery runbook')).toBeVisible()
  expect(screen.getByText('Alex Rivera')).toBeVisible()
  await user.type(screen.getByRole('searchbox'), 'review')
  await waitFor(() => expect(activity).toHaveBeenLastCalledWith({}, expect.objectContaining({ q: 'review', page: 1 }), expect.any(AbortSignal)))
})
