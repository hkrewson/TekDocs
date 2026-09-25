import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLocation } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { Certificates } from './Certificates'
import type { DomainsClient, RegisteredDomain } from './api'

const domain: RegisteredDomain = {
  id: 'domain-1', name: 'example.com', registrar_id: null, registrar: 'Example Registrar', registration_date: null,
  expiration_date: '2027-08-28', renewal_mode: 'auto', owner_id: null, owner: null, status: 'active',
  notes: '', review_state: 'current', observed_expiration_date: '2027-08-28', last_reviewed_at: '2026-08-28T12:00:00Z',
  monitoring_enabled: true, monitor_state: 'current', monitor_error_code: '', last_monitor_at: '2026-08-28T12:00:00Z',
  next_monitor_at: '2026-08-29T12:00:00Z', created_at: '2026-08-28T12:00:00Z',
}
const monitoring = { domain, hostnames: [{ id: 'hostname-1', name: 'mail.example.com' }], runs: [], alerts: [] }
const endpoint = {
  id: 'endpoint-1', domain_id: domain.id, hostname_id: null, target_name: domain.name, protocol: 'https' as const, port: 443,
  monitor_state: 'current' as const, monitor_error_code: '', last_monitor_at: '2026-08-28T12:00:00Z', next_monitor_at: '2026-08-29T12:00:00Z',
  current_leaf_sha256: 'a'.repeat(64), current_not_after: '2027-01-28T12:00:00Z', current_hostname_valid: true, current_trust_valid: true,
}
const certificateHistory = {
  endpoint, alerts: [], runs: [{ id: 'run-1', trigger: 'scheduled' as const, state: 'succeeded' as const, error_code: '',
    leaf_sha256: 'a'.repeat(64), chain_sha256: 'b'.repeat(64), chain_length: 2, subject_common_name: 'example.com', issuer_common_name: 'Example CA', san_count: 1,
    not_before: '2026-07-28T12:00:00Z', not_after: '2027-01-28T12:00:00Z', hostname_valid: true, trust_valid: true,
    tls_version: 'TLSv1.3', cipher_name: 'TLS_AES_256_GCM_SHA384', evidence_digest: 'c'.repeat(64), created_at: '2026-08-28T12:00:00Z', finished_at: '2026-08-28T12:00:01Z' }],
}

function makeClient(overrides: Partial<DomainsClient> = {}): DomainsClient {
  return {
    list: vi.fn().mockResolvedValue([domain]),
    listPage: vi.fn().mockResolvedValue({ results: [domain], page: 1, page_size: 25, count: 1, has_more: false, can_manage: true }),
    create: vi.fn(), monitoring: vi.fn().mockResolvedValue(monitoring), scan: vi.fn(),
    listCertificates: vi.fn().mockResolvedValue([endpoint]), createCertificate: vi.fn().mockResolvedValue(endpoint),
    certificateMonitoring: vi.fn().mockResolvedValue(certificateHistory), scanCertificate: vi.fn().mockResolvedValue(certificateHistory.runs[0]),
    ...overrides,
  }
}

function LocationProbe() {
  return <output data-testid="location">{useLocation().search}</output>
}

function renderView(client: DomainsClient, path = '/certificates') {
  return render(<ApplicationRouter initialPath={path}><Certificates workspace={null} client={client} /><LocationProbe /></ApplicationRouter>)
}

describe('Certificates', () => {
  it('opens a domain drawer, exposes retained evidence, and queues a check', async () => {
    const scanCertificate = vi.fn().mockResolvedValue(certificateHistory.runs[0])
    const user = userEvent.setup()
    renderView(makeClient({ scanCertificate }))

    await user.click(await screen.findByRole('button', { name: 'example.com' }))
    const drawer = await screen.findByRole('dialog', { name: 'Certificates · example.com' })
    expect(within(drawer).getByText('1', { selector: 'dd' })).toBeInTheDocument()
    await user.click(within(drawer).getByRole('button', { name: 'example.com HTTPS certificate' }))
    expect(await within(drawer).findByText(/Example CA/)).toBeInTheDocument()
    expect(within(drawer).getByText('Trusted')).toBeInTheDocument()
    await user.click(within(drawer).getByRole('button', { name: 'Check certificate' }))
    await waitFor(() => expect(scanCertificate).toHaveBeenCalledWith(null, domain.id, endpoint.id))
  })

  it('creates an endpoint and opens its direct history state', async () => {
    const created = { ...endpoint, id: 'endpoint-2', target_name: 'mail.example.com', hostname_id: 'hostname-1', protocol: 'imaps' as const, port: 993 }
    const createCertificate = vi.fn().mockResolvedValue(created)
    const certificateMonitoring = vi.fn().mockResolvedValue({ ...certificateHistory, endpoint: created })
    const user = userEvent.setup()
    renderView(makeClient({ createCertificate, certificateMonitoring }))

    await user.click(await screen.findByRole('button', { name: 'example.com' }))
    const drawer = await screen.findByRole('dialog', { name: 'Certificates · example.com' })
    await user.click(within(drawer).getByRole('button', { name: 'Add endpoint' }))
    await user.selectOptions(within(drawer).getByLabelText('Hostname'), 'hostname-1')
    await user.selectOptions(within(drawer).getByLabelText('Protocol'), 'imaps')
    await user.click(within(drawer).getByRole('button', { name: 'Save endpoint' }))
    await waitFor(() => expect(createCertificate).toHaveBeenCalledWith(null, domain.id, 'imaps', 'hostname-1'))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('endpoint=endpoint-2'))
    expect(await within(drawer).findByRole('heading', { name: 'mail.example.com' })).toBeInTheDocument()
  })

  it('requests a bounded URL collection and restores direct off-page records', async () => {
    const listPage = vi.fn().mockResolvedValue({ results: [], page: 2, page_size: 50, count: 51, has_more: false, can_manage: true })
    const user = userEvent.setup()
    renderView(makeClient({ listPage }), '/certificates?q=example&page=2&page_size=50&domain=domain-1&endpoint=endpoint-1')

    expect(await screen.findByRole('dialog', { name: 'Certificates · example.com' })).toBeInTheDocument()
    await waitFor(() => expect(listPage).toHaveBeenCalledWith(null, { q: 'example', status: '', ordering: 'name', page: 2, pageSize: 50 }, expect.any(AbortSignal)))
    expect(await screen.findByText(/Example CA/)).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('endpoint=endpoint-1')
    await user.click(screen.getByRole('link', { name: 'Back to certificate domains' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('guards dirty endpoint choices and retains them when editing continues', async () => {
    const user = userEvent.setup()
    renderView(makeClient())
    await user.click(await screen.findByRole('button', { name: 'example.com' }))
    const drawer = await screen.findByRole('dialog', { name: 'Certificates · example.com' })
    await user.click(within(drawer).getByRole('button', { name: 'Add endpoint' }))
    await user.selectOptions(within(drawer).getByLabelText('Protocol'), 'imaps')
    await user.click(within(drawer).getByRole('link', { name: 'Back to certificate domains' }))
    const warning = (await screen.findByText('Unsaved changes')).closest('dialog') as HTMLElement
    await user.click(within(warning).getByRole('button', { name: 'Keep editing' }))
    expect(within(drawer).getByLabelText('Protocol')).toHaveValue('imaps')
  })

  it('shows retryable collection and direct-record failures', async () => {
    const collection = renderView(makeClient({ listPage: vi.fn().mockRejectedValue(new Error('internal')) }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Certificate domains could not be loaded.')
    collection.unmount()
    renderView(makeClient({ monitoring: vi.fn().mockRejectedValue(new Error('Domain unavailable.')) }), '/certificates?domain=missing')
    expect(await screen.findByRole('alert')).toHaveTextContent('Domain unavailable.')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
