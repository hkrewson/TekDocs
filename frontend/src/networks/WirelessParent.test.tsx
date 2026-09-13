import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworksClient, WirelessNetwork } from './api'
import { WirelessParent } from './WirelessParent'

const workspace = { kind: 'msp', id: 'msp', name: 'MSP' } as WorkspaceContext
const record = { id: 'ssid-1', subnet_id: 'parent-1', subnet_cidr: '192.0.2.0/24' } as WirelessNetwork
function setup(failed = false, loadFailed = false) {
  const collection = vi.fn().mockResolvedValue({ results: [{ id: 'parent-2', name: 'Branch', cidr: '198.51.100.0/24' }], count: 31, page: 1, page_size: 25, has_more: true })
  if (loadFailed) collection.mockRejectedValueOnce(new Error('Unavailable'))
  const updateWireless = failed ? vi.fn().mockRejectedValue(new Error('Parent is unavailable.')) : vi.fn().mockResolvedValue({ ...record, subnet_id: null })
  const onCancel = vi.fn(), onSaved = vi.fn()
  const client = { collection, updateWireless } as unknown as NetworksClient
  render(<ApplicationRouter><WirelessParent record={record} workspace={workspace} client={client} onSaved={onSaved} onCancel={onCancel} /></ApplicationRouter>)
  return { collection, updateWireless, onSaved, onCancel, user: userEvent.setup() }
}
it('searches bounded parent summaries, retains selection across pages, and sends only the parent change', async () => {
  const { collection, updateWireless, user } = setup()
  await user.selectOptions(await screen.findByLabelText('Matching parent networks'), 'parent-2')
  await user.click(screen.getByRole('button', { name: 'Next' }))
  await waitFor(() => expect(collection).toHaveBeenLastCalledWith(workspace, { q: '', page: 2, page_size: 25, ordering: 'name' }, expect.any(AbortSignal)))
  await user.type(screen.getByRole('searchbox'), 'Branch')
  await user.click(screen.getByRole('button', { name: 'Search' }))
  await waitFor(() => expect(collection).toHaveBeenLastCalledWith(workspace, { q: 'Branch', page: 1, page_size: 25, ordering: 'name' }, expect.any(AbortSignal)))
  await user.click(screen.getByRole('button', { name: 'Save parent network' }))
  expect(updateWireless).toHaveBeenCalledWith(workspace, 'ssid-1', { subnet_id: 'parent-2' })
})
it('preserves a denied parent selection and guards cancel without retrying the mutation', async () => {
  const { user, updateWireless, onCancel } = setup(true)
  await user.selectOptions(await screen.findByLabelText('Matching parent networks'), 'parent-2')
  await user.click(screen.getByRole('button', { name: 'Save parent network' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Parent is unavailable')
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(screen.getByLabelText('Matching parent networks')).toHaveValue('parent-2')
  expect(onCancel).not.toHaveBeenCalled()
  expect(updateWireless).toHaveBeenCalledTimes(1)
})
it('can explicitly remove a parent without fetching or overwriting other associations', async () => {
  const { user, updateWireless, onSaved } = setup()
  await screen.findByLabelText('Matching parent networks')
  await user.click(screen.getByRole('button', { name: 'Use no parent network' }))
  await user.click(screen.getByRole('button', { name: 'Save parent network' }))
  expect(updateWireless).toHaveBeenCalledWith(workspace, 'ssid-1', { subnet_id: null })
  expect(onSaved).toHaveBeenCalledWith({ ...record, subnet_id: null })
})

it('retries failed lookup and handles empty searches without clearing the selected parent', async () => {
  const { user, collection } = setup(false, true)
  expect(await screen.findByRole('alert')).toHaveTextContent('Parent networks could not be loaded')
  await user.click(screen.getByRole('button', { name: 'Try again' }))
  await screen.findByLabelText('Matching parent networks')
  collection.mockResolvedValueOnce({ results: [], count: 0, page: 1, page_size: 25, has_more: false })
  await user.type(screen.getByRole('searchbox'), 'missing')
  await user.click(screen.getByRole('button', { name: 'Search' }))
  expect(await screen.findByText('No parent networks match this search.')).toBeInTheDocument()
  expect(screen.getByText(/192.0.2.0/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Save parent network' })).toBeDisabled()
})
