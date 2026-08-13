import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Domains } from './Domains'
import type { DomainsClient } from './api'

describe('Domains', () => {
  it('creates a workspace-owned registration record', async () => {
    const createDomain = vi.fn().mockResolvedValue({
      id: 'domain-1', name: 'example.com', registrar_id: null, registrar: null,
      registration_date: null, expiration_date: '2027-08-12', renewal_mode: 'auto',
      owner_id: null, owner: null, status: 'active', notes: '', created_at: '2026-08-12T00:00:00Z',
      review_state: 'unreviewed', observed_expiration_date: null, last_reviewed_at: null,
      monitoring_enabled: true, monitor_state: 'never', monitor_error_code: '', last_monitor_at: null,
      next_monitor_at: '2026-08-13T00:00:00Z',
    })
    const client: DomainsClient = {
      list: vi.fn().mockResolvedValue([]),
      create: createDomain,
      monitoring: vi.fn().mockResolvedValue({ domain: {}, runs: [], alerts: [] }),
      scan: vi.fn(),
    }
    const user = userEvent.setup()
    render(<Domains workspace={null} client={client} />)

    await screen.findByText('No registered domains are recorded in this workspace.')
    await user.click(screen.getByRole('button', { name: 'Add domain' }))
    await user.type(screen.getByLabelText('Domain name'), 'example.com')
    await user.selectOptions(screen.getByLabelText('Renewal'), 'auto')
    await user.type(screen.getByLabelText('Expires on'), '2027-08-12')
    await user.click(screen.getByRole('button', { name: 'Save domain' }))

    await waitFor(() => expect(createDomain).toHaveBeenCalledWith(null, expect.objectContaining({
      name: 'example.com', renewal_mode: 'auto', expiration_date: '2027-08-12',
    })))
    expect(await screen.findByText('example.com')).toBeInTheDocument()
  })

  it('shows retained monitoring evidence and queues a new check', async () => {
    const domain = {
      id: 'domain-1', name: 'example.com', registrar_id: null, registrar: null,
      registration_date: null, expiration_date: '2027-08-12', renewal_mode: 'auto' as const,
      owner_id: null, owner: null, status: 'active' as const, notes: '', created_at: '2026-08-12T00:00:00Z',
      review_state: 'current' as const, observed_expiration_date: '2027-08-12', last_reviewed_at: '2026-08-12T01:00:00Z',
      monitoring_enabled: true, monitor_state: 'current' as const, monitor_error_code: '', last_monitor_at: '2026-08-12T01:00:00Z',
      next_monitor_at: '2026-08-13T01:00:00Z',
    }
    const history = {
      domain,
      alerts: [{ id: 'alert-1', kind: 'dns_changed' as const, observed_expiration_date: null, prior_expiration_date: null, created_at: '2026-08-12T01:00:00Z' }],
      runs: [{
        id: 'run-1', trigger: 'scheduled' as const, state: 'succeeded' as const, error_code: '',
        rdap_source: 'rdap.example', observed_expiration_date: '2027-08-12', observed_registrar: 'Registrar',
        dns_source: 'doh.example', dnssec_validated: true, dns_record_count: 4,
        created_at: '2026-08-12T01:00:00Z', finished_at: '2026-08-12T01:00:01Z',
      }],
    }
    const scanDomain = vi.fn().mockResolvedValue(history.runs[0])
    const client: DomainsClient = {
      list: vi.fn().mockResolvedValue([domain]),
      create: vi.fn(),
      monitoring: vi.fn().mockResolvedValue(history),
      scan: scanDomain,
    }
    const user = userEvent.setup()
    render(<Domains workspace={null} client={client} />)

    await user.click(await screen.findByRole('button', { name: 'Details' }))
    expect(await screen.findByText('dns changed')).toBeInTheDocument()
    expect(screen.getByText('4 records via doh.example')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Check now' }))
    await waitFor(() => expect(scanDomain).toHaveBeenCalledWith(null, 'domain-1'))
  })

  it('shows a safe load failure without exposing response internals', async () => {
    const client: DomainsClient = {
      list: vi.fn().mockRejectedValue(new Error('Domains are temporarily unavailable.')),
      create: vi.fn(),
      monitoring: vi.fn(),
      scan: vi.fn(),
    }
    render(<Domains workspace={null} client={client} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Domains are temporarily unavailable.')
  })
})
