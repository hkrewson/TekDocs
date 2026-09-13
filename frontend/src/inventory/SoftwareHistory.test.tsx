import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { vi } from 'vitest'
import { AuthRequestError } from '../auth/api'
import type { ActivityResult, OperationsClient } from '../operations/api'
import type { WorkspaceContext } from '../workspaces/api'
import { SoftwareHistory } from './SoftwareHistory'

const workspace = { kind: 'organization', id: 'client-1' } as WorkspaceContext
const empty: ActivityResult = { results: [], count: 0, page: 1, page_size: 25, has_more: false, actions: [] }
const event = { id: 'event-1', action: 'asset.software.updated', actor_id: null, actor_name: 'Technician', entity_id: 'asset-1', entity_name: 'Software', entity_type: 'asset', request_id: null, occurred_at: '2026-09-12T12:00:00Z' }
function setup(activity: OperationsClient['activity']) {
  const state = { assetListPosition: { y: 123, focus: 'asset-name-asset-1' } }
  const router = createMemoryRouter([{ path: '*', element: <SoftwareHistory assetId="asset-1" workspace={workspace} client={{ activity }} /> }], {
    initialEntries: [{ pathname: '/assets', search: '?record=asset-1&section=history&site=site-1', state }],
  })
  const view = render(<RouterProvider router={router} />)
  return { router, state, ...view }
}

it('requests only the selected record, pages through URL state, and cancels abandoned reads', async () => {
  const user = userEvent.setup()
  let resolvePage: ((value: ActivityResult) => void) | undefined
  const activity = vi.fn<OperationsClient['activity']>().mockResolvedValueOnce({ ...empty, results: [event], count: 26, has_more: true })
    .mockImplementationOnce(() => new Promise((resolve) => { resolvePage = resolve }))
    .mockResolvedValueOnce({ ...empty, results: [event], count: 26, has_more: true })
  const { router, state } = setup(activity)
  expect(await screen.findByText('Installation updated')).toBeVisible()
  expect(activity).toHaveBeenCalledWith({ organizationId: 'client-1' }, { entity_id: 'asset-1', page: 1, page_size: 25 }, expect.any(AbortSignal))
  await user.click(screen.getByRole('button', { name: 'Next' }))
  expect(screen.queryByText('Installation updated')).not.toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Loading history')
  expect(router.state.location.search).toContain('history_page=2')
  expect(router.state.location.search).toContain('site=site-1')
  expect(router.state.location.state).toEqual(state)
  await act(() => router.navigate(-1))
  expect(activity.mock.calls[1]?.[2]?.aborted).toBe(true)
  await act(() => Promise.resolve(resolvePage?.({ ...empty, results: [{ ...event, action: 'stale.event' }] })))
  expect(await screen.findByText('Installation updated')).toBeVisible()
  expect(screen.queryByText('stale event')).not.toBeInTheDocument()
})

it.each([403, 500])('keeps failed %i reads separate from empty history and supports an explicit retry', async (status) => {
  const activity = vi.fn<OperationsClient['activity']>().mockRejectedValueOnce(new AuthRequestError('Failed', status)).mockResolvedValueOnce(empty)
  setup(activity)
  expect(await screen.findByRole('alert')).toHaveTextContent(status === 403 ? 'permission' : 'could not')
  expect(screen.queryByText('No recorded changes are available.')).not.toBeInTheDocument()
  expect(activity).toHaveBeenCalledTimes(1)
  await userEvent.click(screen.getByRole('button', { name: 'Retry history' }))
  await waitFor(() => expect(screen.getByText('No recorded changes are available.')).toBeVisible())
  expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
})
