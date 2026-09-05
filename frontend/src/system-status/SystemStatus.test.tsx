import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import type { SystemDiagnostics, SystemStatusClient } from './api'
import { SystemStatus } from './SystemStatus'

const diagnostics: SystemDiagnostics = {
  status: 'ready',
  checked_at: '2026-09-05T12:00:00Z',
  application_version: '0.8.46',
  database: 'ready',
  diagram_renderer: {
    status: 'ready',
    version: '@mermaid-js/mermaid-cli@11.16.0',
    capacity: 8,
    queue: { waiting: 1, processing: 1, total: 2 },
    recent_failures: [{ code: 'renderer_timeout', occurred_at: Date.parse('2026-09-05T11:30:00Z') }],
    last_checked_at: Date.parse('2026-09-05T11:59:59Z'),
  },
}

it('shows bounded renderer diagnostics and refreshes them', async () => {
  const user = userEvent.setup()
  const load = vi.fn().mockResolvedValue(diagnostics)
  render(<SystemStatus client={{ load }} />)

  expect(await screen.findByText('@mermaid-js/mermaid-cli@11.16.0')).toBeInTheDocument()
  expect(screen.getByText('2 of 8 slots in use')).toBeInTheDocument()
  expect(screen.getByText('renderer_timeout')).toBeInTheDocument()
  expect(screen.getByText(/excludes document content/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Check again' }))
  expect(load).toHaveBeenCalledTimes(2)
})

it('reports an unavailable diagnostic request', async () => {
  const client: SystemStatusClient = { load: vi.fn().mockRejectedValue(new Error('Unavailable')) }
  render(<SystemStatus client={client} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('System status could not be loaded.')
})
