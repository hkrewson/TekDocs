import { afterEach, describe, expect, it, vi } from 'vitest'

import { browserOperationsClient } from './api'

describe('operations API client', () => {
  afterEach(() => vi.restoreAllMocks())

  it('uses exact workspace routes for reminders, calendar export, and activity', async () => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=operations-csrf' })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(new Response(JSON.stringify([]), { status: 200 })))
    const scope = { organizationId: 'client/id' }

    await browserOperationsClient.reminders(scope)
    await browserOperationsClient.createReminder(scope, {
      source_entity_id: 'document/id', domain: 'documentation', kind: 'review', title: 'Review guide',
      due_on: '2026-09-30', lead_days: 14, recurrence: 'none',
    })
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ results: [], count: 0, page: 2, page_size: 50, has_more: false, actions: [] }), { status: 200 }))
    await browserOperationsClient.activity(scope, { q: 'document', page: 2 })

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/workspaces/organizations/client%2Fid/reminders')
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({ method: 'POST' })
    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get('X-CSRFToken')).toBe('operations-csrf')
    expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/v1/workspaces/organizations/client%2Fid/activity?page=2&page_size=50&q=document')
    expect(browserOperationsClient.reminderCalendarUrl(scope)).toBe('/api/v1/workspaces/organizations/client%2Fid/reminders/calendar.ics')
  })
})
