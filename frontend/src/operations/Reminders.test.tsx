import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'

import type { RelationshipsClient } from '../relationships/api'
import type { OperationsClient } from './api'
import { Reminders } from './Reminders'
import { ApplicationRouter } from '../navigation/ApplicationRouter'

it('lists reminders and creates one for a searched workspace record', async () => {
  const reminder = { id: 'reminder-1', source_entity_id: 'doc-1', source: 'Recovery runbook', domain: 'documentation' as const, kind: 'review', title: 'Review recovery runbook', due_on: '2026-09-30', lead_days: 14, recurrence: 'none' as const, owner_id: null, owner: null, active: true, created_at: '2026-08-28T00:00:00Z' }
  const updatedCollection = { results: [reminder, { ...reminder, id: 'reminder-2', title: 'Verify restoration steps' }], count: 2, page: 1, page_size: 25, has_more: false }
  const reminderCollection = vi.fn().mockResolvedValueOnce({ results: [reminder], count: 1, page: 1, page_size: 25, has_more: false }).mockResolvedValue(updatedCollection)
  const createReminder = vi.fn().mockResolvedValue({ ...reminder, id: 'reminder-2', title: 'Verify restoration steps' })
  const client = { reminders: vi.fn(), reminderCollection, createReminder, reminderCalendarUrl: vi.fn().mockReturnValue('/calendar.ics'), activity: vi.fn() } satisfies OperationsClient
  const relationshipsClient = { search: vi.fn().mockResolvedValue({ results: [{ id: 'doc-1', display_name: 'Recovery runbook', entity_type: 'document', visibility: 'msp_private', workspace_label: 'MSP', eligible_link_types: [] }], page: 1, page_size: 15, count: 1, has_more: false }) } as unknown as RelationshipsClient
  const user = userEvent.setup()

  render(<ApplicationRouter initialPath="/deadlines"><Reminders workspace={null} client={client} relationshipsClient={relationshipsClient} /></ApplicationRouter>)
  expect(await screen.findByText('Review recovery runbook')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'New reminder' }))
  await user.type(screen.getByLabelText('Related record'), 'Recovery')
  await user.click(await screen.findByRole('button', { name: /Recovery runbook/ }))
  await user.type(screen.getByLabelText('Title'), 'Verify restoration steps')
  await user.type(screen.getByLabelText('Due date'), '2026-10-31')
  await user.click(screen.getByRole('button', { name: 'Create reminder' }))

  await waitFor(() => expect(createReminder).toHaveBeenCalledWith({}, expect.objectContaining({ source_entity_id: 'doc-1', domain: 'documentation', title: 'Verify restoration steps', due_on: '2026-10-31' })))
  expect(await screen.findByText('Reminder created.')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Download calendar' })).toHaveAttribute('href', '/calendar.ics')
  expect(reminderCollection).toHaveBeenLastCalledWith({}, expect.objectContaining({ page: 1, page_size: 25 }), expect.any(AbortSignal))
})
