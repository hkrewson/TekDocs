import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AssetSiteFilter } from './AssetSiteFilter'
import type { WorkspaceContext } from '../workspaces/api'

const workspace: WorkspaceContext = { kind: 'msp', id: 'installation', name: 'MSP', classifications: [], capabilities: [], organization: null }
const result = { results: [{ id: 'site-1', name: 'Main office' }], selected: null, page: 1, page_size: 25, count: 31, has_more: true }

describe('asset site filter', () => {
  it('searches the authorized collection and pages choices without changing the selected filter', async () => {
    const client = vi.fn().mockResolvedValue(result)
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<AssetSiteFilter workspace={workspace} value="" onChange={onChange} client={client} />)
    await user.click(await screen.findByRole('button', { name: 'Next' }))
    await waitFor(() => expect(client).toHaveBeenLastCalledWith(workspace, '', 2, '', expect.any(AbortSignal)))
    await user.type(screen.getByLabelText('Search sites'), 'Remote')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(client).toHaveBeenLastCalledWith(workspace, 'Remote', 1, '', expect.any(AbortSignal)))
    expect(onChange).not.toHaveBeenCalled()
    await user.click(await screen.findByRole('radio', { name: 'Main office' }))
    expect(onChange).toHaveBeenCalledWith('site-1')
  })

  it('retains an unavailable selected condition and supports explicit retry or clearing', async () => {
    const client = vi.fn().mockRejectedValueOnce(new Error('denied')).mockResolvedValue({ ...result, results: [], count: 0, has_more: false })
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<AssetSiteFilter workspace={workspace} value="missing" onChange={onChange} client={client} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Site choices could not be loaded')
    expect(onChange).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Site unavailable or no longer used by assets')).toBeInTheDocument()
    expect(screen.getByText('No matching sites.')).toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: 'All' }))
    expect(onChange).toHaveBeenCalledWith('')
  })
})
