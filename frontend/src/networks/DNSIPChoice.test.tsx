import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { DNSIPChoice } from './DNSIPChoice'
import type { NetworksClient } from './api'
import type { WorkspaceContext } from '../workspaces/api'
const workspace = { kind: 'msp', id: 'msp' } as WorkspaceContext
it('searches and pages IP choices, disables the wrong family, and retains a selection outside this page', async () => {
  const user = userEvent.setup(), onChange = vi.fn()
  const addressCollection = vi.fn().mockResolvedValue({ results: [{ id: 'ip4', address: '192.0.2.10', address_family: 4 }, { id: 'ip6', address: '2001:db8::1', address_family: 6 }], count: 31, has_more: true, page: 1, page_size: 25 })
  render(<DNSIPChoice workspace={workspace} client={{ addressCollection } as unknown as NetworksClient} family={4} selectedId="off-page" onChange={onChange} />)
  expect(await screen.findByRole('option', { name: '2001:db8::1' })).toBeDisabled()
  expect(screen.getByText(/An IP inventory record is linked/)).toBeVisible()
  await user.type(screen.getByRole('searchbox'), '192.0.2')
  await user.click(screen.getByRole('button', { name: 'Search' }))
  await waitFor(() => expect(addressCollection).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ q: '192.0.2', page_size: 25, page: 1 }), expect.any(AbortSignal)))
  await user.click(screen.getByRole('button', { name: 'Next' }))
  await waitFor(() => expect(addressCollection).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ page: 2 }), expect.any(AbortSignal)))
  await user.selectOptions(screen.getByLabelText('Linked IP inventory', { selector: 'select' }), 'ip4')
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ id: 'ip4', address: '192.0.2.10' }))
  await user.click(screen.getByRole('button', { name: 'Remove IP link' }))
  expect(onChange).toHaveBeenLastCalledWith(null)
})
