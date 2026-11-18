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
  expect(screen.getByLabelText('Search reminders')).toBeVisible()
  expect(screen.queryByLabelText('Rows per page')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'New reminder' }))
  expect(screen.queryByRole('button', { name: 'New reminder' })).not.toBeInTheDocument()
  await user.type(screen.getByLabelText('Related record'), 'Recovery')
  await user.click(await screen.findByRole('button', { name: /Recovery runbook/ }))
  const options = screen.getByText('Options').closest('details')
  expect(options).not.toHaveAttribute('open')
  await user.click(screen.getByText('Options'))
  expect(screen.getByLabelText('Area')).toHaveValue('documentation')
  await user.type(screen.getByLabelText('Title'), 'Verify restoration steps')
  await user.type(screen.getByLabelText('Due date'), '2026-10-31')
  await user.click(screen.getByRole('button', { name: 'Create reminder' }))

  await waitFor(() => expect(createReminder).toHaveBeenCalledWith({}, expect.objectContaining({ source_entity_id: 'doc-1', domain: 'documentation', title: 'Verify restoration steps', due_on: '2026-10-31' })))
  expect(await screen.findByText('Reminder created.')).toBeVisible()
  expect(screen.queryByRole('link', { name: 'Download calendar' })).not.toBeVisible()
  await user.click(screen.getByText('More'))
  expect(screen.getByRole('link', { name: 'Download calendar' })).toHaveAttribute('href', '/calendar.ics')
  expect(reminderCollection).toHaveBeenLastCalledWith({}, expect.objectContaining({ page: 1, page_size: 25 }), expect.any(AbortSignal))
})

it('offers only supported records, derives their area, and preserves optional entries after a failed save', async () => {
  const collection = { results: [], count: 0, page: 1, page_size: 25, has_more: false }
  const reminder = { id: 'reminder-2', source_entity_id: 'asset-1', source: 'Core switch', domain: 'inventory' as const, kind: 'review', title: 'Review switch lifecycle', due_on: '2026-11-30', lead_days: 7, recurrence: 'annual' as const, owner_id: null, owner: null, active: true, created_at: '2026-08-28T00:00:00Z' }
  const createReminder = vi.fn().mockRejectedValueOnce(new Error('denied')).mockResolvedValue(reminder)
  const client = { reminders: vi.fn(), reminderCollection: vi.fn().mockResolvedValue(collection), createReminder, reminderCalendarUrl: vi.fn().mockReturnValue('/calendar.ics'), activity: vi.fn() } satisfies OperationsClient
  const relationshipsClient = { search: vi.fn().mockResolvedValue({ results: [
    { id: 'organization-1', display_name: 'Acme clinic', entity_type: 'organization', visibility: 'msp_private', workspace_label: 'MSP', eligible_link_types: [] },
    { id: 'asset-1', display_name: 'Core switch', entity_type: 'client_asset', visibility: 'msp_private', workspace_label: 'MSP', eligible_link_types: [] },
  ], page: 1, page_size: 15, count: 2, has_more: false }) } as unknown as RelationshipsClient
  const user = userEvent.setup()

  render(<ApplicationRouter initialPath="/deadlines"><Reminders workspace={null} client={client} relationshipsClient={relationshipsClient} /></ApplicationRouter>)
  await screen.findByText('No active reminders are scheduled for this workspace.')
  expect(screen.queryByLabelText('Search reminders')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Filters' })).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Rows per page')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'New reminder' }))
  await user.type(screen.getByLabelText('Related record'), 'switch')
  expect(await screen.findByRole('button', { name: /Core switch/ })).toBeVisible()
  expect(screen.queryByRole('button', { name: /Acme clinic/ })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /Core switch/ }))
  await user.click(screen.getByText('Options'))
  expect(screen.getByLabelText('Area')).toHaveValue('inventory')
  await user.clear(screen.getByLabelText('Advance notice in days'))
  await user.type(screen.getByLabelText('Advance notice in days'), '7')
  await user.selectOptions(screen.getByLabelText('Repeats'), 'annual')
  await user.type(screen.getByLabelText('Title'), 'Review switch lifecycle')
  await user.type(screen.getByLabelText('Due date'), '2026-11-30')
  await user.click(screen.getByRole('button', { name: 'Create reminder' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('The reminder wasn’t created. Your entries are still here. Try again.')
  expect(screen.getByLabelText('Title')).toHaveValue('Review switch lifecycle')
  expect(screen.getByLabelText('Advance notice in days')).toHaveValue(7)
  await user.click(screen.getByRole('button', { name: 'Create reminder' }))
  await waitFor(() => expect(createReminder).toHaveBeenLastCalledWith({}, expect.objectContaining({ source_entity_id: 'asset-1', domain: 'inventory', lead_days: 7, recurrence: 'annual' })))
})

it('recovers a failed record search and explains when no compatible records match', async () => {
  const collection = { results: [], count: 0, page: 1, page_size: 25, has_more: false }
  const client = { reminders: vi.fn(), reminderCollection: vi.fn().mockResolvedValue(collection), createReminder: vi.fn(), reminderCalendarUrl: vi.fn().mockReturnValue('/calendar.ics'), activity: vi.fn() } satisfies OperationsClient
  const relationshipsClient = { search: vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ results: [{ id: 'organization-1', display_name: 'Acme clinic', entity_type: 'organization', visibility: 'msp_private', workspace_label: 'MSP', eligible_link_types: [] }], page: 1, page_size: 15, count: 1, has_more: false }) } as unknown as RelationshipsClient
  const user = userEvent.setup()

  render(<ApplicationRouter initialPath="/deadlines?new=1"><Reminders workspace={null} client={client} relationshipsClient={relationshipsClient} /></ApplicationRouter>)
  await user.type(screen.getByLabelText('Related record'), 'Acme')
  expect(await screen.findByRole('alert')).toHaveTextContent('Related records couldn’t be searched.')
  await user.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('No records that support reminders match this search.')).toBeVisible()
})

it('keeps a filtered empty schedule recoverable and becomes quiet after clearing filters', async () => {
  const collection = { results: [], count: 0, page: 1, page_size: 25, has_more: false }
  const reminderCollection = vi.fn().mockResolvedValue(collection)
  const client = { reminders: vi.fn(), reminderCollection, createReminder: vi.fn(), reminderCalendarUrl: vi.fn().mockReturnValue('/calendar.ics'), activity: vi.fn() } satisfies OperationsClient
  const relationshipsClient = { search: vi.fn() } as unknown as RelationshipsClient
  const user = userEvent.setup()

  render(<ApplicationRouter initialPath="/deadlines?q=missing&domain=documentation"><Reminders workspace={null} client={client} relationshipsClient={relationshipsClient} /></ApplicationRouter>)
  expect(await screen.findByText('No reminders match these filters.')).toBeVisible()
  expect(screen.getByLabelText('Search reminders')).toHaveValue('missing')
  expect(screen.getByRole('button', { name: 'Filters (2)' })).toBeVisible()
  expect(screen.queryByLabelText('Rows per page')).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Clear filters' }))
  expect(await screen.findByText('No active reminders are scheduled for this workspace.')).toBeVisible()
  await waitFor(() => expect(reminderCollection).toHaveBeenLastCalledWith({}, expect.objectContaining({ q: '', domain: '' }), expect.any(AbortSignal)))
  expect(screen.queryByLabelText('Search reminders')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Filters' })).not.toBeInTheDocument()
})
