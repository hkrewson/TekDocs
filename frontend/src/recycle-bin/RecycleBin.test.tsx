import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { RecycleBin } from './RecycleBin'
import type { RecycleBinClient } from './api'

const item = {
  id: '00000000-0000-4000-8000-000000000020',
  record_type: 'site' as const,
  label: 'Downtown office',
  archived_at: '2026-08-08T18:00:00Z',
  workspace_kind: 'msp' as const,
  workspace_id: '00000000-0000-4000-8000-000000000002',
  workspace_name: 'Example MSP',
  cascade_count: 3,
  can_restore: true,
}

describe('RecycleBin', () => {
  it('lists archived records, confirms cascade scope, and refreshes after restore', async () => {
    const user = userEvent.setup()
    const list = vi.fn()
      .mockResolvedValueOnce({ results: [item], page: 1, page_size: 50, count: 1, has_more: false })
      .mockResolvedValueOnce({ results: [], page: 1, page_size: 50, count: 0, has_more: false })
    const restore = vi.fn().mockResolvedValue(undefined)
    const client = { list, restore } as RecycleBinClient

    render(<RecycleBin workspace={null} client={client} />)

    expect(await screen.findByText('Downtown office')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Restore' }))
    expect(screen.getByText('This also restores 2 records archived in the same cascade.')).toBeInTheDocument()
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Restore' }))
    await screen.findByText('Downtown office restored.')
    await screen.findByText('This workspace has no recoverable archived records.')
    expect(restore).toHaveBeenCalledWith({}, expect.objectContaining({ id: item.id, record_type: 'site' }))
    await vi.waitFor(() => expect(list).toHaveBeenCalledTimes(2))
  })

  it('explains when a record is visible but cannot be restored', async () => {
    const client = { list: vi.fn().mockResolvedValue({ results: [{ ...item, can_restore: false }], page: 1, page_size: 50, count: 1, has_more: false }), restore: vi.fn() } as unknown as RecycleBinClient
    render(<RecycleBin workspace={null} client={client} />)

    const button = await screen.findByRole('button', { name: 'Restore' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('title', 'You do not have permission to restore this record')
  })
})
