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
    listProviders: vi.fn().mockResolvedValue([
      { key: 'netbox', label: 'NetBox', version: '1.0', direction: 'read_only', credential_fields: [{ key: 'api_token', label: 'API token', secret: true, minimum_length: 8, input_type: 'password', help_text: '' }], capabilities: ['inventory_observations', 'reconciliation'], object_types: ['ipam.vlan'], pagination: 'opaque_cursor', minimum_sync_interval_minutes: 5, maximum_sync_interval_minutes: 10080, health_states: ['unknown', 'healthy', 'degraded', 'failing', 'paused'], observation_schema_version: 1, default_base_url: '', base_url_editable: true, setup_help_url: '' },
      { key: 'microsoft_graph', label: 'Microsoft 365', version: '1.0', direction: 'read_only', credential_fields: [{ key: 'tenant_id', label: 'Microsoft tenant ID', secret: false, minimum_length: 36, input_type: 'text', help_text: 'The directory ID.' }, { key: 'client_id', label: 'Application (client) ID', secret: false, minimum_length: 36, input_type: 'text', help_text: 'The application ID.' }, { key: 'client_secret', label: 'Client secret', secret: true, minimum_length: 8, input_type: 'password', help_text: 'Stored encrypted.' }], capabilities: ['identity_observations'], object_types: ['user'], pagination: 'opaque_cursor', minimum_sync_interval_minutes: 15, maximum_sync_interval_minutes: 10080, health_states: ['unknown', 'healthy', 'degraded', 'failing', 'paused'], observation_schema_version: 1, default_base_url: 'https://graph.microsoft.com/v1.0/', base_url_editable: false, setup_help_url: 'https://learn.microsoft.com/' },
      { key: 'halopsa', label: 'HaloPSA', version: '1.0', direction: 'read_only', credential_fields: [{ key: 'client_id', label: 'Client ID', secret: false, minimum_length: 1, input_type: 'text', help_text: 'Dedicated Halo API application client ID.' }, { key: 'client_secret', label: 'Client secret', secret: true, minimum_length: 8, input_type: 'password', help_text: 'Stored encrypted.' }], capabilities: ['psa_observations', 'external_ticket_search', 'reconciliation'], object_types: ['client', 'site', 'contact', 'contract', 'ticket'], pagination: 'opaque_cursor', minimum_sync_interval_minutes: 15, maximum_sync_interval_minutes: 10080, health_states: ['unknown', 'healthy', 'degraded', 'failing', 'paused'], observation_schema_version: 1, default_base_url: '', base_url_editable: true, setup_help_url: 'https://halopsa.com/guides/article/?kbid=1499' },
    ]),
    listConnections: vi.fn().mockResolvedValue([]), createConnection: vi.fn(), updateConnection: vi.fn(),
    rotateConnection: vi.fn(), startSync: vi.fn(),
    listJobs: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 50, count: 0, has_more: false }),
    cancelJob: vi.fn(),
    listLogs: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 50, count: 0, has_more: false }),
    listObservations: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 50, count: 0, has_more: false }),
    listConflicts: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 50, count: 0, has_more: false }),
    resolveConflict: vi.fn(), listGitExports: vi.fn().mockResolvedValue([]), createGitExport: vi.fn(),
    gitExportDownloadUrl: vi.fn().mockReturnValue('/download'),
    listHaloTickets: vi.fn().mockResolvedValue([]),
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
      provider_details: {},
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
    vi.mocked(provider.cancelJob).mockResolvedValue({
      id: 'job-2', connection_id: connection.id, connection_name: connection.name, trigger: 'manual',
      state: 'cancelled', attempts: 0, cursor_present: false, last_error_code: '', result_counts: {},
      available_at: '2026-08-12T00:00:00Z', started_at: null, finished_at: '2026-08-12T00:00:01Z',
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
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(provider.cancelJob).toHaveBeenCalledWith(workspace, expect.objectContaining({ id: 'job-2' })))
    await user.click(screen.getByRole('button', { name: 'Pause' }))
    await waitFor(() => expect(provider.updateConnection).toHaveBeenCalledWith(workspace, connection, false))
    await user.click(screen.getByRole('button', { name: /Rotate Primary NetBox provider credential/i }))
    await waitFor(() => expect(provider.rotateConnection).toHaveBeenCalledWith(
      workspace, expect.objectContaining({ id: connection.id }), { api_token: 'replacement-token' },
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
      provider_details: {},
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
      credentials: { api_token: 'one-time-token' }, sync_interval_minutes: 30,
    }))
    expect(container.querySelector('input[type="password"]')).not.toBeInTheDocument()
  })

  it('uses provider-defined Microsoft fields and never asks for an editable Graph URL', async () => {
    const provider = providerClient()
    vi.mocked(provider.createConnection).mockResolvedValue({
      id: 'connection-ms', provider: 'microsoft_graph', name: 'Client Microsoft 365',
      base_url: 'https://graph.microsoft.com/v1.0/', provider_details: { tenant_id: '11111111-1111-1111-1111-111111111111', permission_status: 'not_validated' },
      credential_configured: true, secret_generation: 1, active: true, sync_interval_minutes: 15,
      health_status: 'unknown', last_successful_sync_at: null, last_error_code: '', rate_limit_reset_at: null,
      reconciliation_counts: {}, next_sync_at: '2026-08-12T00:00:00Z', created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z',
    })
    const user = userEvent.setup()
    render(<Integrations workspace={workspace} client={webhookClient} documentsClient={documentsClient()} providerClient={provider} />)

    await user.click(await screen.findByRole('button', { name: 'New connection' }))
    await user.selectOptions(screen.getByLabelText('Provider'), 'microsoft_graph')
    expect(screen.queryByLabelText('API base URL')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Name'), 'Client Microsoft 365')
    await user.type(screen.getByLabelText(/Microsoft tenant ID/), '11111111-1111-1111-1111-111111111111')
    await user.type(screen.getByLabelText(/Application \(client\) ID/), '22222222-2222-2222-2222-222222222222')
    await user.type(screen.getByLabelText(/Client secret/), 'microsoft-client-secret')
    await user.click(screen.getByRole('button', { name: 'Save connection' }))

    await waitFor(() => expect(provider.createConnection).toHaveBeenCalledWith(workspace, {
      provider: 'microsoft_graph', name: 'Client Microsoft 365', base_url: 'https://graph.microsoft.com/v1.0/',
      credentials: { tenant_id: '11111111-1111-1111-1111-111111111111', client_id: '22222222-2222-2222-2222-222222222222', client_secret: 'microsoft-client-secret' },
      sync_interval_minutes: 15,
    }))
  })

  it('uses the HaloPSA base URL and dedicated client credentials', async () => {
    const provider = providerClient()
    vi.mocked(provider.createConnection).mockResolvedValue({
      id: 'connection-halo', provider: 'halopsa', name: 'Primary HaloPSA',
      base_url: 'https://support.example.com/', provider_details: { client_id: 'tekdocs-reader' },
      credential_configured: true, secret_generation: 1, active: true, sync_interval_minutes: 30,
      health_status: 'unknown', last_successful_sync_at: null, last_error_code: '', rate_limit_reset_at: null,
      reconciliation_counts: {}, next_sync_at: '2026-08-12T00:00:00Z', created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z',
    })
    const user = userEvent.setup()
    render(<Integrations workspace={workspace} client={webhookClient} documentsClient={documentsClient()} providerClient={provider} />)

    await user.click(await screen.findByRole('button', { name: 'New connection' }))
    await user.selectOptions(screen.getByLabelText('Provider'), 'halopsa')
    await user.type(screen.getByLabelText('Name'), 'Primary HaloPSA')
    await user.type(screen.getByLabelText('API base URL'), 'https://support.example.com/')
    await user.type(screen.getByLabelText(/^Client ID/), 'tekdocs-reader')
    await user.type(screen.getByLabelText(/Client secret/), 'halo-client-secret')
    await user.clear(screen.getByLabelText('Sync interval (minutes)'))
    await user.type(screen.getByLabelText('Sync interval (minutes)'), '30')
    await user.click(screen.getByRole('button', { name: 'Save connection' }))

    await waitFor(() => expect(provider.createConnection).toHaveBeenCalledWith(workspace, {
      provider: 'halopsa', name: 'Primary HaloPSA', base_url: 'https://support.example.com/',
      credentials: { client_id: 'tekdocs-reader', client_secret: 'halo-client-secret' },
      sync_interval_minutes: 30,
    }))
  })
})
