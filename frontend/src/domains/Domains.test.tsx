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
      monitoring: vi.fn().mockResolvedValue({ domain: {}, runs: [], alerts: [], hostnames: [] }),
      scan: vi.fn(),
      listCertificates: vi.fn().mockResolvedValue([]),
      createCertificate: vi.fn(),
      certificateMonitoring: vi.fn(),
      scanCertificate: vi.fn(),
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
      hostnames: [{ id: 'hostname-1', name: 'mail.example.com' }],
      alerts: [{ id: 'alert-1', kind: 'dns_changed' as const, observed_expiration_date: null, prior_expiration_date: null, created_at: '2026-08-12T01:00:00Z' }],
      runs: [{
        id: 'run-1', trigger: 'scheduled' as const, state: 'succeeded' as const, error_code: '',
        rdap_source: 'rdap.example', observed_expiration_date: '2027-08-12', observed_registrar: 'Registrar',
        dns_source: 'doh.example', dnssec_validated: true, dns_record_count: 4,
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
      alerts: [{ id: 'certificate-alert-1', kind: 'expiration_due' as const, created_at: '2026-08-12T01:00:02Z' }],
      runs: [{
        id: 'certificate-run-1', trigger: 'scheduled' as const, state: 'succeeded' as const, error_code: '',
        leaf_sha256: 'a'.repeat(64), chain_sha256: 'b'.repeat(64), chain_length: 2,
        subject_common_name: 'example.com', issuer_common_name: 'Example CA', san_count: 1,
        not_before: '2026-07-12T01:00:00Z', not_after: '2026-09-12T01:00:00Z',
        hostname_valid: true, trust_valid: false, tls_version: 'TLSv1.3', cipher_name: 'TLS_AES_256_GCM_SHA384',
        created_at: '2026-08-12T01:00:00Z', finished_at: '2026-08-12T01:00:01Z',
      }],
    }
    const createdCertificate = {
      ...certificate, id: 'certificate-2', hostname_id: 'hostname-1', target_name: 'mail.example.com',
      protocol: 'imaps' as const, port: 993, monitor_state: 'never' as const, last_monitor_at: null,
      current_leaf_sha256: '', current_not_after: null, current_hostname_valid: null, current_trust_valid: null,
    }
    const createCertificate = vi.fn().mockResolvedValue(createdCertificate)
    const scanCertificate = vi.fn().mockResolvedValue(certificateHistory.runs[0])
    const scanDomain = vi.fn().mockResolvedValue(history.runs[0])
    const client: DomainsClient = {
      list: vi.fn().mockResolvedValue([domain]),
      create: vi.fn(),
      monitoring: vi.fn().mockResolvedValue(history),
      scan: scanDomain,
      listCertificates: vi.fn().mockResolvedValue([certificate]),
      createCertificate,
      certificateMonitoring: vi.fn().mockResolvedValue(certificateHistory),
      scanCertificate,
    }
    const user = userEvent.setup()
    render(<Domains workspace={null} client={client} />)

    await user.click(await screen.findByRole('button', { name: 'Details' }))
    expect(await screen.findByText('dns changed')).toBeInTheDocument()
    expect(screen.getByText('4 records via doh.example')).toBeInTheDocument()
    expect(screen.getByText('TLS certificate endpoints')).toBeInTheDocument()
    expect(screen.getByText('Untrusted')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'History' }))
    expect(await screen.findByText('Example CA')).toBeInTheDocument()
    expect(screen.getByText('expiration due')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Check certificate' }))
    await waitFor(() => expect(scanCertificate).toHaveBeenCalledWith(null, domain.id, certificate.id))
    await user.click(screen.getByRole('button', { name: 'Add endpoint' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await user.click(screen.getByRole('button', { name: 'Add endpoint' }))
    await user.selectOptions(screen.getByLabelText('Hostname'), 'hostname-1')
    await user.selectOptions(screen.getByLabelText('Protocol'), 'imaps')
    await user.click(screen.getByRole('button', { name: 'Save endpoint' }))
    await waitFor(() => expect(createCertificate).toHaveBeenCalledWith(null, domain.id, 'imaps', 'hostname-1'))
    expect(await screen.findByText('mail.example.com')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Check now' }))
    await waitFor(() => expect(scanDomain).toHaveBeenCalledWith(null, 'domain-1'))
  })

  it('shows a safe load failure without exposing response internals', async () => {
    const client: DomainsClient = {
      list: vi.fn().mockRejectedValue(new Error('Domains are temporarily unavailable.')),
      create: vi.fn(),
      monitoring: vi.fn(),
      scan: vi.fn(),
      listCertificates: vi.fn(),
      createCertificate: vi.fn(),
      certificateMonitoring: vi.fn(),
      scanCertificate: vi.fn(),
    }
    render(<Domains workspace={null} client={client} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Domains are temporarily unavailable.')
  })

  it('keeps a scoped domain visible when its monitoring history is unavailable', async () => {
    const domain = {
      id: 'domain-1', name: 'example.com', registrar_id: null, registrar: null,
      registration_date: null, expiration_date: null, renewal_mode: 'manual' as const,
      owner_id: null, owner: null, status: 'active' as const, notes: '', created_at: '2026-08-12T00:00:00Z',
      review_state: 'unreviewed' as const, observed_expiration_date: null, last_reviewed_at: null,
      monitoring_enabled: true, monitor_state: 'never' as const, monitor_error_code: '', last_monitor_at: null,
      next_monitor_at: '2026-08-13T00:00:00Z',
    }
    const client: DomainsClient = {
      list: vi.fn().mockResolvedValue([domain]), create: vi.fn(),
      monitoring: vi.fn().mockRejectedValue(new Error('Monitoring is temporarily unavailable.')),
      scan: vi.fn(), listCertificates: vi.fn().mockResolvedValue([]), createCertificate: vi.fn(),
      certificateMonitoring: vi.fn(), scanCertificate: vi.fn(),
    }
    const user = userEvent.setup()
    render(<Domains workspace={null} client={client} />)
    await user.click(await screen.findByRole('button', { name: 'Details' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Monitoring is temporarily unavailable.')
    expect(screen.getByText('example.com')).toBeInTheDocument()
  })
})
