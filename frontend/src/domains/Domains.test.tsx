import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLocation } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { Domains } from './Domains'
import type { DomainsClient, RegisteredDomain } from './api'

const domain: RegisteredDomain = {
  id: 'domain-1', name: 'example.com', registrar_id: null, registrar: 'Example Registrar',
  registration_date: null, expiration_date: '2027-08-12', renewal_mode: 'auto',
  owner_id: null, owner: null, status: 'active', notes: 'Primary public domain.', created_at: '2026-08-12T00:00:00Z',
  review_state: 'current', observed_expiration_date: '2027-08-12', last_reviewed_at: '2026-08-12T01:00:00Z',
  monitoring_enabled: true, monitor_state: 'current', monitor_error_code: '', last_monitor_at: '2026-08-12T01:00:00Z',
  next_monitor_at: '2026-08-13T01:00:00Z',
}

const history = {
  domain,
  hostnames: [{ id: 'hostname-1', name: 'mail.example.com' }],
  alerts: [{ id: 'alert-1', kind: 'dns_changed' as const, observed_expiration_date: null, prior_expiration_date: null, created_at: '2026-08-12T01:00:00Z' }],
  runs: [{
    id: 'run-1', trigger: 'scheduled' as const, state: 'succeeded' as const, error_code: '',
    rdap_source: 'rdap.example', observed_expiration_date: '2027-08-12', observed_registrar: 'Registrar',
    dns_source: 'doh.example', dnssec_validated: true, dns_record_count: 4,
    caa_record_count: 1, evidence_digest: 'c'.repeat(64),
    created_at: '2026-08-12T01:00:00Z', finished_at: '2026-08-12T01:00:01Z',
  }],
}

const certificate = {
  id: 'certificate-1', domain_id: domain.id, hostname_id: null, target_name: domain.name,
  protocol: 'https' as const, port: 443, monitor_state: 'current' as const, monitor_error_code: '',
  last_monitor_at: '2026-08-12T01:00:00Z', next_monitor_at: '2026-08-13T01:00:00Z',
  current_leaf_sha256: 'a'.repeat(64), current_not_after: '2026-09-12T01:00:00Z',
  current_hostname_valid: true, current_trust_valid: false,
}

const certificateHistory = {
  endpoint: certificate,
  alerts: [{ id: 'certificate-alert-1', kind: 'expiration_due', observed_not_after: null, prior_not_after: null, created_at: '2026-08-12T01:00:02Z' }],
  runs: [{
    id: 'certificate-run-1', trigger: 'scheduled' as const, state: 'succeeded' as const, error_code: '',
    leaf_sha256: 'a'.repeat(64), chain_sha256: 'b'.repeat(64), chain_length: 2,
    subject_common_name: 'example.com', issuer_common_name: 'Example CA', san_count: 1,
    not_before: '2026-07-12T01:00:00Z', not_after: '2026-09-12T01:00:00Z',
    hostname_valid: true, trust_valid: false, tls_version: 'TLSv1.3', cipher_name: 'TLS_AES_256_GCM_SHA384',
    evidence_digest: 'd'.repeat(64), created_at: '2026-08-12T01:00:00Z', finished_at: '2026-08-12T01:00:01Z',
  }],
}

function makeClient(overrides: Partial<DomainsClient> = {}): DomainsClient {
  return {
    list: vi.fn().mockResolvedValue([domain]),
    listPage: vi.fn().mockResolvedValue({ results: [domain], page: 1, page_size: 25, count: 1, has_more: false, can_manage: true }),
    create: vi.fn().mockResolvedValue(domain),
    monitoring: vi.fn().mockResolvedValue(history),
    scan: vi.fn().mockResolvedValue(history.runs[0]),
    listCertificates: vi.fn().mockResolvedValue([certificate]),
    createCertificate: vi.fn().mockResolvedValue(certificate),
    certificateMonitoring: vi.fn().mockResolvedValue(certificateHistory),
    scanCertificate: vi.fn().mockResolvedValue(certificateHistory.runs[0]),
    ...overrides,
  }
}

function renderDomains(client: DomainsClient, entry = '/domains') {
  return render(<ApplicationRouter initialPath={entry}><Domains workspace={null} client={client} /><LocationProbe /></ApplicationRouter>)
}

function LocationProbe() {
  return <output data-testid="location">{useLocation().search}</output>
}

describe('Domains', () => {
  it('creates a workspace-owned registration record in the drawer', async () => {
    const create = vi.fn().mockResolvedValue(domain)
    const client = makeClient({
      listPage: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 25, count: 0, has_more: false, can_manage: true }),
      create,
    })
    const user = userEvent.setup()
    renderDomains(client)

    await screen.findByText('No registered domains are recorded in this workspace.')
    await user.click(screen.getByRole('button', { name: 'Add domain' }))
    await user.type(screen.getByLabelText('Domain name'), 'example.com')
    await user.selectOptions(screen.getByLabelText('Renewal'), 'auto')
    await user.type(screen.getByLabelText('Expires on'), '2027-08-12')
    await user.click(screen.getByRole('button', { name: 'Save domain' }))

    await waitFor(() => expect(create).toHaveBeenCalledWith(null, expect.objectContaining({
      name: 'example.com', renewal_mode: 'auto', expiration_date: '2027-08-12',
    })))
    expect(await screen.findByRole('heading', { name: 'example.com' })).toBeInTheDocument()
  })

  it('opens a useful record drawer and keeps domain and certificate operations available', async () => {
    const createCertificate = vi.fn().mockResolvedValue({
      ...certificate, id: 'certificate-2', hostname_id: 'hostname-1', target_name: 'mail.example.com',
      protocol: 'imaps' as const, port: 993, monitor_state: 'never' as const, last_monitor_at: null,
      current_leaf_sha256: '', current_not_after: null, current_hostname_valid: null, current_trust_valid: null,
    })
    const scanCertificate = vi.fn().mockResolvedValue(certificateHistory.runs[0])
    const scan = vi.fn().mockResolvedValue(history.runs[0])
    const client = makeClient({ createCertificate, scanCertificate, scan })
    const user = userEvent.setup()
    renderDomains(client)

    await user.click(await screen.findByRole('button', { name: 'example.com' }))
    expect(await screen.findByText('Primary public domain.')).toBeInTheDocument()
    expect(screen.getByText('dns changed')).toBeInTheDocument()
    expect(screen.getByText('4 DNS records · DNSSEC validated')).toBeInTheDocument()
    expect(screen.getByText('TLS endpoints')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /example\.comHTTPS/i }))
    expect(await screen.findByText(/Example CA/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Check certificate' }))
    await waitFor(() => expect(scanCertificate).toHaveBeenCalledWith(null, domain.id, certificate.id))
    await user.click(screen.getByRole('button', { name: 'Add endpoint' }))
    await user.selectOptions(screen.getByLabelText('Hostname'), 'hostname-1')
    await user.selectOptions(screen.getByLabelText('Protocol'), 'imaps')
    await user.click(screen.getByRole('button', { name: 'Save endpoint' }))
    await waitFor(() => expect(createCertificate).toHaveBeenCalledWith(null, domain.id, 'imaps', 'hostname-1'))
    expect(await screen.findByText('mail.example.com')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Check now' }))
    await waitFor(() => expect(scan).toHaveBeenCalledWith(null, domain.id))
  })

  it('retains collection state in the URL and requests the bounded full collection query', async () => {
    const listPage = vi.fn().mockResolvedValue({ results: [domain], page: 2, page_size: 50, count: 51, has_more: false, can_manage: true })
    const user = userEvent.setup()
    renderDomains(makeClient({ listPage }), '/domains?q=example&status=active&ordering=-expiration_date&page=2&page_size=50')

    await screen.findByRole('button', { name: 'example.com' })
    expect(listPage).toHaveBeenCalledWith(null, {
      q: 'example', status: 'active', ordering: '-expiration_date', page: 2, pageSize: 50,
    }, expect.any(AbortSignal))
    await user.click(screen.getByRole('button', { name: 'example.com' }))
    await screen.findByRole('dialog')
    expect(screen.getByTestId('location')).toHaveTextContent('domain=domain-1')
  })

  it('shows a safe collection failure', async () => {
    renderDomains(makeClient({ listPage: vi.fn().mockRejectedValue(new Error('internal response')) }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Domains are temporarily unavailable.')
    expect(screen.queryByText('internal response')).not.toBeInTheDocument()
  })

  it('keeps the selected collection row visible when its detail is unavailable', async () => {
    const user = userEvent.setup()
    renderDomains(makeClient({ monitoring: vi.fn().mockRejectedValue(new Error('Monitoring is temporarily unavailable.')) }))
    await user.click(await screen.findByRole('button', { name: 'example.com' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Monitoring is temporarily unavailable.')
    expect(screen.getByRole('button', { name: 'example.com' })).toBeInTheDocument()
  })

  it('loads a direct off-page record and guards dirty create dismissal', async () => {
    const user = userEvent.setup()
    const client = makeClient({
      listPage: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 25, count: 0, has_more: false, can_manage: true }),
    })
    const direct = renderDomains(client, '/domains?domain=domain-1')
    expect(await screen.findByRole('heading', { name: 'example.com' })).toBeInTheDocument()
    direct.unmount()

    renderDomains(client, '/domains?domain=new')
    await user.type(await screen.findByLabelText('Domain name'), 'dirty.example')
    await user.click(screen.getByRole('link', { name: 'Back to domains' }))
    const warning = (await screen.findByText('Unsaved changes')).closest('dialog') as HTMLElement
    await user.click(within(warning).getByRole('button', { name: 'Keep editing' }))
    expect(screen.getByLabelText('Domain name')).toHaveValue('dirty.example')
    await user.click(screen.getByRole('link', { name: 'Back to domains' }))
    await user.click(within((await screen.findByText('Unsaved changes')).closest('dialog') as HTMLElement).getByRole('button', { name: 'Discard changes' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
})
