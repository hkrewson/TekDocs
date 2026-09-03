/* eslint-disable @typescript-eslint/unbound-method */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { DocumentsClient, DocumentRecord } from '../documentation/api'
import type { WorkspaceContext } from '../workspaces/api'
import type { WebhooksClient } from './api'
import { Integrations } from './Integrations'
import type { IntegrationsClient } from './providerApi'

const workspace: WorkspaceContext = {
  kind: 'organization', id: 'client-1', name: 'Acme Dental', classifications: ['client'],
  capabilities: ['overview', 'integrations'], organization: null,
}

function providerClient(): IntegrationsClient {
  return {
    listProviders: vi.fn().mockResolvedValue([{ key: 'netbox', label: 'NetBox', version: '1.0', direction: 'read_only', credential_fields: [{ key: 'api_token', label: 'API token', secret: true, minimum_length: 8 }], capabilities: ['inventory_observations', 'reconciliation'], object_types: ['ipam.vlan'], pagination: 'opaque_cursor', minimum_sync_interval_minutes: 5, maximum_sync_interval_minutes: 10080, health_states: ['unknown', 'healthy', 'degraded', 'failing', 'paused'], observation_schema_version: 1 }]),
    listConnections: vi.fn().mockResolvedValue([]), createConnection: vi.fn(), updateConnection: vi.fn(),
    rotateConnection: vi.fn(), startSync: vi.fn(),
    listJobs: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 50, count: 0, has_more: false }),
    listLogs: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 50, count: 0, has_more: false }),
    listConflicts: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 50, count: 0, has_more: false }),
    resolveConflict: vi.fn(), listGitExports: vi.fn().mockResolvedValue([]), createGitExport: vi.fn(),
    gitExportDownloadUrl: vi.fn().mockReturnValue('/download'),
  }
}

const webhookClient = {
  listEndpoints: vi.fn().mockResolvedValue([]), createEndpoint: vi.fn(), setActive: vi.fn(), rotate: vi.fn(),
  listDeliveries: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 25, count: 0, has_more: false }),
  retry: vi.fn(),
} satisfies WebhooksClient

const runbook = {
  id: 'document-1', title: 'Switch replacement runbook', category: 'guide', is_template: false, publications: [],
} as unknown as DocumentRecord

function documentsClient(): DocumentsClient {
  return { list: vi.fn().mockResolvedValue({ results: [runbook], count: 1 }) } as unknown as DocumentsClient
}

describe('Integrations', () => {
  it('loads the exact workspace and creates a selected sanitized export', async () => {
    const provider = providerClient()
    vi.mocked(provider.createGitExport).mockResolvedValue({
      id: 'bundle-1', selection_manifest: { documents: [], publications: [] },
      content_digest: 'a'.repeat(64), byte_size: 512, created_at: '2026-08-12T00:00:00Z',
    })
    const documents = documentsClient()
    const user = userEvent.setup()

    render(<Integrations workspace={workspace} client={webhookClient} documentsClient={documents} providerClient={provider} />)

    expect(await screen.findByText(/No external provider connections/i)).toBeInTheDocument()
    expect(provider.listConnections).toHaveBeenCalledWith(workspace, expect.any(AbortSignal))
    expect(documents.list).toHaveBeenCalledWith({ organizationId: 'client-1' }, expect.any(AbortSignal))

    await user.click(screen.getByRole('button', { name: 'Git exports' }))
    await user.click(screen.getByRole('checkbox', { name: /Switch replacement runbook/i }))
    await user.click(screen.getByRole('button', { name: 'Create bundle' }))

    await waitFor(() => expect(provider.createGitExport).toHaveBeenCalledWith(workspace, ['document-1'], []))
    expect(await screen.findByText('1 KiB')).toBeInTheDocument()
  })

  it('manages provider state and records an explicit reconciliation decision', async () => {
    const provider = providerClient()
    const connection = {
      id: 'connection-1', provider: 'netbox', name: 'Primary NetBox', base_url: 'https://netbox.example.com/api/',
      credential_configured: true, secret_generation: 1, active: true, sync_interval_minutes: 60,
      health_status: 'healthy', last_successful_sync_at: '2026-08-12T00:00:01Z', last_error_code: '', rate_limit_reset_at: null, reconciliation_counts: { observations: 3 },
      next_sync_at: '2026-08-12T01:00:00Z', created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z',
    } as const
    const conflict = {
      id: 'conflict-1', connection_id: connection.id, connection_name: connection.name,
      local_entity_id: 'entity-1', remote_type: 'ipam.vlan', remote_id: '42', difference: 'changed',
      status: 'open', created_at: '2026-08-12T00:00:00Z', resolved_at: null,
    } as const
    vi.mocked(provider.listConnections).mockResolvedValue([connection])
    vi.mocked(provider.listJobs).mockResolvedValue({
      results: [{ id: 'job-1', connection_id: connection.id, connection_name: connection.name, trigger: 'manual', state: 'succeeded', attempts: 1, cursor_present: false, last_error_code: '', result_counts: { observations: 3 }, available_at: '2026-08-12T00:00:00Z', started_at: '2026-08-12T00:00:00Z', finished_at: '2026-08-12T00:00:01Z', created_at: '2026-08-12T00:00:00Z' }],
      page: 1, page_size: 50, count: 1, has_more: false,
    })
    vi.mocked(provider.listLogs).mockResolvedValue({
      results: [{ id: 'log-1', connection_id: connection.id, connection_name: connection.name, job_id: 'job-1', level: 'info', code: 'sync_completed', metrics: { observations: 3 }, occurred_at: '2026-08-12T00:00:01Z' }],
      page: 1, page_size: 50, count: 1, has_more: false,
    })
    vi.mocked(provider.listConflicts).mockResolvedValue({ results: [conflict], page: 1, page_size: 50, count: 1, has_more: false })
    vi.mocked(provider.startSync).mockResolvedValue({
      id: 'job-2', connection_id: connection.id, connection_name: connection.name, trigger: 'manual',
      state: 'pending', attempts: 0, cursor_present: false, last_error_code: '', result_counts: {},
      available_at: '2026-08-12T00:00:00Z', started_at: null, finished_at: null,
      created_at: '2026-08-12T00:00:00Z',
    })
    vi.mocked(provider.updateConnection).mockResolvedValue({ ...connection, active: false })
    vi.mocked(provider.rotateConnection).mockResolvedValue({ ...connection, secret_generation: 2 })
    vi.mocked(provider.resolveConflict).mockResolvedValue({ ...conflict, status: 'accept_remote', resolved_at: '2026-08-12T01:00:00Z' })
    vi.spyOn(window, 'prompt').mockReturnValue('replacement-token')
    const user = userEvent.setup()

    render(<Integrations workspace={workspace} client={webhookClient} documentsClient={documentsClient()} providerClient={provider} />)

    await user.click(await screen.findByRole('button', { name: 'Sync' }))
    await waitFor(() => expect(provider.startSync).toHaveBeenCalledWith(workspace, connection))
    await user.click(screen.getByRole('button', { name: 'Pause' }))
    await waitFor(() => expect(provider.updateConnection).toHaveBeenCalledWith(workspace, connection, false))
    await user.click(screen.getByRole('button', { name: /Rotate Primary NetBox provider credential/i }))
    await waitFor(() => expect(provider.rotateConnection).toHaveBeenCalledWith(
      workspace, expect.objectContaining({ id: connection.id }), 'replacement-token',
    ))

    await user.click(screen.getByRole('button', { name: 'Reconciliation' }))
    await user.click(screen.getByRole('button', { name: 'Accept fingerprint' }))
    await waitFor(() => expect(provider.resolveConflict).toHaveBeenCalledWith(workspace, conflict, 'accept_remote'))
    expect(screen.getByText(/No unresolved provider differences/i)).toBeInTheDocument()
  })

  it('creates a read-only provider connection and clears the one-time token field', async () => {
    const provider = providerClient()
    vi.mocked(provider.createConnection).mockResolvedValue({
      id: 'connection-new', provider: 'netbox', name: 'Client NetBox', base_url: 'https://netbox.example.com/api/',
      credential_configured: true, secret_generation: 1, active: true, sync_interval_minutes: 30,
      health_status: 'unknown', last_successful_sync_at: null, last_error_code: '', rate_limit_reset_at: null, reconciliation_counts: {},
      next_sync_at: '2026-08-12T00:00:00Z', created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z',
    })
    const user = userEvent.setup()

    const { container } = render(<Integrations workspace={workspace} client={webhookClient} documentsClient={documentsClient()} providerClient={provider} />)
    await user.click(await screen.findByRole('button', { name: 'New connection' }))
    await user.type(screen.getByLabelText('Name'), 'Client NetBox')
    await user.type(screen.getByLabelText('API base URL'), 'https://netbox.example.com/api/')
    await user.type(screen.getByLabelText(/API token/), 'one-time-token')
    await user.clear(screen.getByLabelText('Sync interval (minutes)'))
    await user.type(screen.getByLabelText('Sync interval (minutes)'), '30')
    await user.click(screen.getByRole('button', { name: 'Save connection' }))

    await waitFor(() => expect(provider.createConnection).toHaveBeenCalledWith(workspace, {
      provider: 'netbox', name: 'Client NetBox', base_url: 'https://netbox.example.com/api/',
      api_token: 'one-time-token', sync_interval_minutes: 30,
    }))
    expect(container.querySelector('input[type="password"]')).not.toBeInTheDocument()
  })
})
