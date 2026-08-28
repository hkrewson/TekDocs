import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { Certificates } from './Certificates'
import type { DomainsClient } from './api'

const domain = {
  id: 'domain-1', name: 'example.com', registrar_id: null, registrar: null, registration_date: null,
  expiration_date: '2027-08-28', renewal_mode: 'auto' as const, owner_id: null, owner: null, status: 'active' as const,
  notes: '', review_state: 'current' as const, observed_expiration_date: '2027-08-28', last_reviewed_at: '2026-08-28T12:00:00Z',
  monitoring_enabled: true, monitor_state: 'current' as const, monitor_error_code: '', last_monitor_at: '2026-08-28T12:00:00Z',
  next_monitor_at: '2026-08-29T12:00:00Z', created_at: '2026-08-28T12:00:00Z',
}
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

describe('Certificates', () => {
  it('opens a domain, exposes retained certificate evidence, and queues a check', async () => {
    const scanCertificate = vi.fn().mockResolvedValue(certificateHistory.runs[0])
    const client = {
      list: vi.fn().mockResolvedValue([domain]),
      monitoring: vi.fn().mockResolvedValue({ domain, hostnames: [], runs: [], alerts: [] }),
      listCertificates: vi.fn().mockResolvedValue([endpoint]),
      certificateMonitoring: vi.fn().mockResolvedValue(certificateHistory),
      scanCertificate,
    } as unknown as DomainsClient
    const user = userEvent.setup()
    render(<MemoryRouter><Certificates workspace={null} client={client} /></MemoryRouter>)

    await user.click(await screen.findByRole('button', { name: /example.com/ }))
    expect(await screen.findByText('Trusted')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'History' }))
    expect(await screen.findByText('Example CA')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Check certificate' }))
    await waitFor(() => expect(scanCertificate).toHaveBeenCalledWith(null, domain.id, endpoint.id))
  })
})
