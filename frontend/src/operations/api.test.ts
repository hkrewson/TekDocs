import { afterEach, describe, expect, it, vi } from 'vitest'

import { browserOperationsClient } from './api'

describe('operations API client', () => {
  afterEach(() => vi.restoreAllMocks())

  it('uses exact workspace routes for reminders, calendar export, and activity', async () => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=operations-csrf' })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(new Response(JSON.stringify([]), { status: 200 })))
    const scope = { organizationId: 'client/id' }

    await browserOperationsClient.reminders(scope)
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ results: [], count: 0, page: 2, page_size: 50, has_more: false }), { status: 200 }))
    await browserOperationsClient.reminderCollection(scope, { q: 'review', domain: 'documentation', ordering: '-due_on', page: 2, page_size: 50 })
    await browserOperationsClient.createReminder(scope, {
      source_entity_id: 'document/id', domain: 'documentation', kind: 'review', title: 'Review guide',
      due_on: '2026-09-30', lead_days: 14, recurrence: 'none',
    })
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ results: [], count: 0, page: 2, page_size: 50, has_more: false, actions: [] }), { status: 200 }))
    await browserOperationsClient.activity(scope, { q: 'document', page: 2 })

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/workspaces/organizations/client%2Fid/reminders')
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/workspaces/organizations/client%2Fid/reminders?paginated=true&q=review&ordering=-due_on&page=2&page_size=50&domain=documentation')
    expect(fetchMock.mock.calls[2]?.[1]).toMatchObject({ method: 'POST' })
    expect(new Headers(fetchMock.mock.calls[2]?.[1]?.headers).get('X-CSRFToken')).toBe('operations-csrf')
    expect(fetchMock.mock.calls[3]?.[0]).toBe('/api/v1/workspaces/organizations/client%2Fid/activity?page=2&page_size=50&q=document')
    const controller = new AbortController()
    await browserOperationsClient.activity(scope, { entity_id: 'asset/id', handoff_id: 'handoff/id', page_size: 25 }, controller.signal)
    expect(fetchMock.mock.calls[4]?.[0]).toBe('/api/v1/workspaces/organizations/client%2Fid/activity?page=1&page_size=25&entity_id=asset%2Fid&handoff_id=handoff%2Fid')
    expect(fetchMock.mock.calls[4]?.[1]?.signal).toBe(controller.signal)
    expect(browserOperationsClient.reminderCalendarUrl(scope)).toBe('/api/v1/workspaces/organizations/client%2Fid/reminders/calendar.ics')
  })
})
