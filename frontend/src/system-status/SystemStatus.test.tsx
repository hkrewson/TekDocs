import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import type { SystemDiagnostics, SystemStatusClient } from './api'
import { SystemStatus } from './SystemStatus'

const diagnostics: SystemDiagnostics = {
  status: 'ready',
  checked_at: '2026-09-05T12:00:00Z',
  application_version: '0.9.0',
  database: 'ready',
  valkey: 'ready',
  diagram_renderer: {
    status: 'ready',
    version: '@mermaid-js/mermaid-cli@11.16.0',
    capacity: 8,
    queue: { waiting: 1, processing: 1, total: 2 },
    recent_failures: [{ code: 'renderer_timeout', occurred_at: Date.parse('2026-09-05T11:30:00Z') }],
    last_checked_at: Date.parse('2026-09-05T11:59:59Z'),
  },
  repositories: {
    status: 'ready',
    total: 2,
    healthy: 2,
    degraded: 0,
    blocked: 0,
    unknown: 0,
    states: { never: 0, matched: 2, missing: 0, advanced: 0, mismatched: 0, corrupt: 0, unavailable: 0 },
    last_checked_at: '2026-09-05T11:59:59Z',
    repair: null,
  },
}

it('shows bounded renderer diagnostics and refreshes them', async () => {
  const user = userEvent.setup()
  const load = vi.fn().mockResolvedValue(diagnostics)
  render(<SystemStatus client={{ load }} />)

  expect(await screen.findByText('@mermaid-js/mermaid-cli@11.16.0')).toBeInTheDocument()
  expect(screen.getByText('Diagram service').closest('li')).toHaveTextContent('2 of 8 slots in use · 1 waiting, 1 processing')
  expect(screen.getByText('renderer_timeout')).toBeInTheDocument()
  expect(screen.getByText('Workspace repositories').closest('li')).toHaveTextContent('2 of 2 healthy')
  expect(screen.getByText('Background jobs (Valkey)').closest('li')).toHaveTextContent('Ready')
  expect(screen.getByText(/does not include documents/)).toBeInTheDocument()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Check again' }))
  expect(load).toHaveBeenCalledTimes(2)
})

it('reports an unavailable request and retries without reloading the page', async () => {
  const user = userEvent.setup()
  const load = vi.fn().mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValue(diagnostics)
  const client: SystemStatusClient = { load }
  render(<SystemStatus client={client} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('System status could not be loaded.')
  await user.click(screen.getByRole('button', { name: 'Retry' }))
  expect(await screen.findByText('@mermaid-js/mermaid-cli@11.16.0')).toBeInTheDocument()
  expect(load).toHaveBeenCalledTimes(2)
})

it('keeps service details visible when the system is degraded', async () => {
  const client: SystemStatusClient = { load: vi.fn().mockResolvedValue({ ...diagnostics, status: 'degraded', valkey: 'unavailable', diagram_renderer: { ...diagnostics.diagram_renderer, status: 'stale' }, repositories: { ...diagnostics.repositories, status: 'degraded', healthy: 1, degraded: 1, repair: 'reconcile_to_accepted' } }) }
  render(<SystemStatus client={client} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('services need attention')
  expect(screen.getByText('Check overdue')).toBeInTheDocument()
  expect(screen.getByText('Version 0.9.0')).toBeInTheDocument()
  expect(screen.getByText('Needs attention')).toBeInTheDocument()
  expect(screen.getByText(/Writes are paused/)).toBeInTheDocument()
  expect(screen.getByText('Background jobs (Valkey)').closest('li')).toHaveTextContent('Unavailable')
})
