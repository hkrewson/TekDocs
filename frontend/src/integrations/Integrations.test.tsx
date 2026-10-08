/* eslint-disable @typescript-eslint/unbound-method */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { DocumentsClient, DocumentRecord } from '../documentation/api'
import { NavigationGuardProvider } from '../navigation/NavigationGuardProvider'
import type { NetworksClient } from '../networks/api'
import type { InventoryClient } from '../inventory/api'
import type { WorkspaceContext } from '../workspaces/api'
import type { WebhooksClient } from './api'
import { Integrations } from './Integrations'
import { IntegrationRequestError } from './providerApi'
import type { IntegrationConflict, IntegrationConnection, IntegrationsClient } from './providerApi'

const workspace: WorkspaceContext = {
  kind: 'organization', id: 'client-1', name: 'Acme Dental', classifications: ['client'],
  capabilities: ['overview', 'integrations'], organization: null,
}

function providerClient(): IntegrationsClient {
  return {
    listProviders: vi.fn().mockResolvedValue([
      { key: 'netbox', label: 'NetBox', version: '1.0', direction: 'read_only', credential_fields: [{ key: 'api_token', label: 'API token', secret: true, minimum_length: 8, input_type: 'password', help_text: '' }], capabilities: ['inventory_observations', 'reconciliation'], object_types: ['ipam.vlan'], pagination: 'opaque_cursor', minimum_sync_interval_minutes: 5, maximum_sync_interval_minutes: 10080, health_states: ['unknown', 'healthy', 'degraded', 'failing', 'paused'], observation_schema_version: 1, default_base_url: '', base_url_editable: true, setup_help_url: '' },
      { key: 'unifi', label: 'UniFi Network', version: '1.0', direction: 'read_only', credential_fields: [{ key: 'api_key', label: 'API key', secret: true, minimum_length: 8, input_type: 'password', help_text: 'Create a read-only API key.' }], capabilities: ['network_observations', 'device_observations', 'client_observations', 'wireless_observations'], object_types: ['unifi.network', 'unifi.device', 'unifi.client', 'unifi.wifi'], pagination: 'opaque_cursor', minimum_sync_interval_minutes: 5, maximum_sync_interval_minutes: 10080, health_states: ['unknown', 'healthy', 'degraded', 'failing', 'paused'], observation_schema_version: 1, default_base_url: '', base_url_editable: true, setup_help_url: 'https://help.ui.com/' },
      { key: 'microsoft_graph', label: 'Microsoft 365', version: '1.0', direction: 'read_only', credential_fields: [{ key: 'tenant_id', label: 'Microsoft tenant ID', secret: false, minimum_length: 36, input_type: 'text', help_text: 'The directory ID.' }, { key: 'client_id', label: 'Application (client) ID', secret: false, minimum_length: 36, input_type: 'text', help_text: 'The application ID.' }, { key: 'client_secret', label: 'Client secret', secret: true, minimum_length: 8, input_type: 'password', help_text: 'Stored encrypted.' }], capabilities: ['identity_observations'], object_types: ['user'], pagination: 'opaque_cursor', minimum_sync_interval_minutes: 15, maximum_sync_interval_minutes: 10080, health_states: ['unknown', 'healthy', 'degraded', 'failing', 'paused'], observation_schema_version: 1, default_base_url: 'https://graph.microsoft.com/v1.0/', base_url_editable: false, setup_help_url: 'https://learn.microsoft.com/' },
      { key: 'halopsa', label: 'HaloPSA', version: '1.0', direction: 'read_only', credential_fields: [{ key: 'client_id', label: 'Client ID', secret: false, minimum_length: 1, input_type: 'text', help_text: 'Dedicated Halo API application client ID.' }, { key: 'client_secret', label: 'Client secret', secret: true, minimum_length: 8, input_type: 'password', help_text: 'Stored encrypted.' }], capabilities: ['psa_observations', 'external_ticket_search', 'reconciliation'], object_types: ['client', 'site', 'contact', 'contract', 'ticket'], pagination: 'opaque_cursor', minimum_sync_interval_minutes: 15, maximum_sync_interval_minutes: 10080, health_states: ['unknown', 'healthy', 'degraded', 'failing', 'paused'], observation_schema_version: 1, default_base_url: '', base_url_editable: true, setup_help_url: 'https://halopsa.com/guides/article/?kbid=1499' },
      { key: 'ninjaone', label: 'NinjaOne', version: '1.0', direction: 'read_only', credential_fields: [{ key: 'client_id', label: 'API application client ID', secret: false, minimum_length: 8, input_type: 'text', help_text: 'From Administration → Apps → API in NinjaOne.' }, { key: 'client_secret', label: 'API application client secret', secret: true, minimum_length: 8, input_type: 'password', help_text: 'Stored encrypted.' }], capabilities: ['rmm_observations', 'asset_reconciliation', 'software_observations'], object_types: ['organization', 'location', 'device_status', 'device', 'operating_system', 'health', 'software'], pagination: 'opaque_cursor', minimum_sync_interval_minutes: 15, maximum_sync_interval_minutes: 10080, health_states: ['unknown', 'healthy', 'degraded', 'failing', 'paused'], observation_schema_version: 1, default_base_url: 'https://app.ninjarmm.com/', base_url_editable: true, setup_help_url: 'https://www.ninjaone.com/docs/application-programming-interface-api/oauth-token-configuration/' },
    ]),
    listConnections: vi.fn().mockResolvedValue([]), createConnection: vi.fn(), updateConnection: vi.fn(),
    rotateConnection: vi.fn(), configureNetBoxWriteCredential: vi.fn(), previewNetBoxPublication: vi.fn(), publishNetBoxProposal: vi.fn(), startSync: vi.fn(),
    listJobs: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 50, count: 0, has_more: false }),
    cancelJob: vi.fn(),
    listLogs: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 50, count: 0, has_more: false }),
    listObservations: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 50, count: 0, has_more: false }),
    listConflicts: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 50, count: 0, has_more: false }),
    resolveConflict: vi.fn(), adoptNetBoxConflict: vi.fn(), listGitExports: vi.fn().mockResolvedValue([]), createGitExport: vi.fn(),
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

function setup(provider: IntegrationsClient, documents = documentsClient(), path = '/workspaces/organizations/client-1/integrations', authClient = { reauthenticate: vi.fn().mockResolvedValue(undefined) }, networksClient?: NetworksClient, inventoryClient?: InventoryClient) {
  const router = createMemoryRouter([{
    path: '*',
    element: <NavigationGuardProvider><Integrations workspace={workspace} client={webhookClient} documentsClient={documents} providerClient={provider} networksClient={networksClient} inventoryClient={inventoryClient} authClient={authClient} /></NavigationGuardProvider>,
  }], { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return router
}

describe('Integrations', () => {
  it('exposes each integration workflow as a durable link and loads only the active section', async () => {
    const provider = providerClient()
    const documents = documentsClient()

    setup(provider, documents)

    expect(await screen.findByRole('link', { name: 'Connections' })).toHaveAttribute('href', '/workspaces/organizations/client-1/integrations')
    expect(screen.getByRole('link', { name: 'Imports' })).toHaveAttribute('href', '/workspaces/organizations/client-1/integrations?section=imports')
    expect(documents.list).not.toHaveBeenCalled()
    expect(provider.listGitExports).not.toHaveBeenCalled()
  })

  it('loads the exact workspace and creates a selected sanitized export', async () => {
    const provider = providerClient()
    vi.mocked(provider.createGitExport).mockResolvedValue({
      id: 'bundle-1', selection_manifest: { documents: [], publications: [] },
      content_digest: 'a'.repeat(64), byte_size: 512, created_at: '2026-08-12T00:00:00Z',
    })
    const documents = documentsClient()
    const user = userEvent.setup()

    setup(provider, documents)

    expect(await screen.findByText(/No systems are connected/i)).toBeInTheDocument()
    expect(provider.listConnections).toHaveBeenCalledWith(workspace, expect.any(AbortSignal))
    expect(documents.list).not.toHaveBeenCalled()

    await user.click(screen.getByRole('link', { name: 'Git exports' }))
    await waitFor(() => expect(documents.list).toHaveBeenCalledWith({ organizationId: 'client-1' }, expect.any(AbortSignal)))
    await user.click(await screen.findByRole('checkbox', { name: /Switch replacement runbook/i }))
    await user.click(screen.getByRole('button', { name: 'Create bundle' }))

    await waitFor(() => expect(provider.createGitExport).toHaveBeenCalledWith(workspace, ['document-1'], [], false))
    expect(await screen.findByText('1 KiB')).toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: /Switch replacement runbook/i }))
    await user.click(screen.getByRole('checkbox', { name: 'Include all accepted repository Markdown' }))
    await user.click(screen.getByRole('button', { name: 'Create bundle' }))
    await waitFor(() => expect(provider.createGitExport).toHaveBeenCalledWith(workspace, ['document-1'], [], true))
  })

  it('creates a repository-only snapshot and preserves the choice after a failed attempt', async () => {
    const provider = providerClient()
    const documents = { list: vi.fn().mockResolvedValue({ results: [], count: 0 }) } as unknown as DocumentsClient
    const user = userEvent.setup()
    vi.mocked(provider.createGitExport)
      .mockRejectedValueOnce(new IntegrationRequestError('Repository is not indexed.', 400))
      .mockResolvedValueOnce({
        id: 'repository-bundle',
        selection_manifest: {
          documents: [], publications: [],
          repository: {
            accepted_commit: 'abcdef1234567890', snapshot_only: true,
            files: [
              { path: 'repository/documents/one.md', content_id: 'one', kind: 'document', sha256: 'a'.repeat(64) },
              { path: 'repository/fragments/two.md', content_id: 'two', kind: 'fragment', sha256: 'b'.repeat(64) },
            ],
          },
        },
        content_digest: 'c'.repeat(64), byte_size: 1024, created_at: '2026-10-08T00:00:00Z',
      })
    setup(provider, documents)

    await user.click(screen.getByRole('link', { name: 'Git exports' }))
    const checkbox = await screen.findByRole('checkbox', { name: 'Include all accepted repository Markdown' })
    expect(screen.getByText(/not a backup/i)).toBeInTheDocument()
    expect(screen.getByText(/No legacy documents are available/i)).toBeInTheDocument()
    const create = screen.getByRole('button', { name: 'Create bundle' })
    expect(create).toBeDisabled()
    checkbox.focus()
    await user.keyboard(' ')
    expect(create).toBeEnabled()
    await user.click(screen.getByRole('link', { name: 'Imports' }))
    await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
    expect(checkbox).toBeChecked()

    await user.click(create)
    expect(await screen.findByRole('alert')).toHaveTextContent('The export could not be created')
    expect(checkbox).toBeChecked()
    expect(provider.createGitExport).toHaveBeenCalledWith(workspace, [], [], true)

    await user.click(create)
    expect(await screen.findByText('2 Markdown files')).toBeInTheDocument()
    expect(screen.getByText('Git version abcdef123456')).toBeInTheDocument()
    expect(checkbox).not.toBeChecked()
    expect(create).toBeDisabled()
  })

  it('keeps repository export available when legacy document choices fail to load', async () => {
    const provider = providerClient()
    const documents = { list: vi.fn().mockRejectedValue(new Error('Legacy documents unavailable')) } as unknown as DocumentsClient
    const user = userEvent.setup()
    vi.mocked(provider.createGitExport).mockResolvedValue({
      id: 'repository-bundle',
      selection_manifest: { documents: [], publications: [], repository: { accepted_commit: 'abcdef1234567890', snapshot_only: true, files: [] } },
      content_digest: 'c'.repeat(64), byte_size: 1024, created_at: '2026-10-08T00:00:00Z',
    })
    setup(provider, documents)

    await user.click(screen.getByRole('link', { name: 'Git exports' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Legacy document choices could not be loaded')
    const checkbox = screen.getByRole('checkbox', { name: 'Include all accepted repository Markdown' })
    await user.click(checkbox)
    await user.click(screen.getByRole('button', { name: 'Create bundle' }))

    await waitFor(() => expect(provider.createGitExport).toHaveBeenCalledWith(workspace, [], [], true))
  })

  it('protects a connection draft during section navigation and retries a failed collection', async () => {
    const provider = providerClient()
    const availableProviders = await providerClient().listProviders(workspace, new AbortController().signal)
    vi.mocked(provider.listProviders).mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValueOnce(availableProviders)
    const user = userEvent.setup()
    const router = setup(provider)

    expect(await screen.findByRole('alert')).toHaveTextContent('Integrations could not be loaded.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await user.click(await screen.findByRole('button', { name: 'New connection' }))
    await user.type(screen.getByLabelText('Name'), 'Draft connection')
    await user.click(screen.getByRole('link', { name: 'Imports' }))
    await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
    expect(router.state.location.search).toBe('')
    expect(screen.getByLabelText('Name')).toHaveValue('Draft connection')
    await user.click(screen.getByRole('link', { name: 'Imports' }))
    await user.click(await screen.findByRole('button', { name: 'Discard changes' }))
    await waitFor(() => expect(router.state.location.search).toBe('?section=imports'))
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
    const user = userEvent.setup()

    const router = setup(provider)

    await user.click(await screen.findByRole('button', { name: 'Sync' }))
    await waitFor(() => expect(provider.startSync).toHaveBeenCalledWith(workspace, connection))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(provider.cancelJob).toHaveBeenCalledWith(workspace, expect.objectContaining({ id: 'job-2' })))
    await user.click(screen.getByRole('button', { name: 'Pause' }))
    await waitFor(() => expect(provider.updateConnection).toHaveBeenCalledWith(workspace, connection, {
      active: false, sync_interval_minutes: 60,
    }))
    await user.click(screen.getByRole('button', { name: /Replace the credential for Primary NetBox/i }))
    const credential = screen.getByRole('alertdialog')
    expect(credential).toHaveTextContent('The current credential will stop working after this change.')
    await user.type(screen.getByLabelText('API token'), 'replacement-token')
    await user.click(screen.getByRole('button', { name: 'Replace credential' }))
    await waitFor(() => expect(provider.rotateConnection).toHaveBeenCalledWith(
      workspace, expect.objectContaining({ id: connection.id }), { api_token: 'replacement-token' },
    ))

    await user.click(screen.getByRole('link', { name: 'Reconciliation' }))
    await waitFor(() => expect(provider.listConflicts).toHaveBeenCalledWith(workspace, {
      page: 1, page_size: 25, q: '', remote_type: '', status: 'open',
    }, expect.any(AbortSignal)))
    await user.type(screen.getByRole('searchbox', { name: 'Search records needing review' }), 'arrakis')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(provider.listConflicts).toHaveBeenLastCalledWith(workspace, {
      page: 1, page_size: 25, q: 'arrakis', remote_type: '', status: 'open',
    }, expect.any(AbortSignal)))
    expect(router.state.location.search).toContain('review_search=arrakis')
    await user.click(screen.getByRole('button', { name: 'Acknowledge change' }))
    await waitFor(() => expect(provider.resolveConflict).toHaveBeenCalledWith(workspace, conflict, 'accept_remote'))
    expect(screen.getByText(/No differences match these filters/i)).toBeInTheDocument()
  })

  it('links an ambiguous supported NetBox prefix to an existing TekDocs network', async () => {
    const provider = providerClient()
    const conflict: IntegrationConflict = {
      id: 'conflict-prefix', connection_id: 'connection-1', connection_name: 'Primary NetBox', connection_provider: 'netbox',
      local_entity_id: null, provider_values: { prefix: '10.42.0.0/24' }, remote_type: 'ipam.prefix', remote_id: '41', difference: 'unmatched',
      status: 'open', created_at: '2026-08-12T00:00:00Z', resolved_at: null,
    }
    vi.mocked(provider.listConflicts).mockResolvedValue({ results: [conflict], page: 1, page_size: 25, count: 1, has_more: false })
    vi.mocked(provider.adoptNetBoxConflict).mockResolvedValue({ ...conflict, local_entity_id: 'network-1', local_entity_name: '10.42.0.0/24', status: 'accept_remote', resolved_at: '2026-08-12T01:00:00Z' })
    const networks = {
      netBoxChoiceCollection: vi.fn().mockResolvedValue({
        results: [{ id: 'network-1', name: '10.42.0.0/24', entity_type: 'network_subnet', object_type: 'ipam.prefix', linked: false }],
        selected: null, page: 1, page_size: 25, count: 1, has_more: false, can_manage: true,
      }),
    } as unknown as NetworksClient
    const user = userEvent.setup()

    setup(provider, documentsClient(), '/workspaces/organizations/client-1/integrations?section=reconciliation', undefined, networks)
    await user.click(await screen.findByRole('button', { name: 'Link to TekDocs' }))
    expect(screen.getByRole('heading', { name: 'Link NetBox record' })).toBeInTheDocument()
    expect(screen.queryByText(/Create a TekDocs/i)).not.toBeInTheDocument()
    await user.click(await screen.findByRole('radio', { name: /10.42.0.0\/24/i }))
    await user.click(screen.getByRole('button', { name: 'Link record' }))

    await waitFor(() => expect(provider.adoptNetBoxConflict).toHaveBeenCalledWith(workspace, conflict, { entity_id: 'network-1' }))
  })

  it('reviews the exact current UniFi proposal before publishing it to NetBox', async () => {
    const provider = providerClient()
    const connection = {
      id: 'connection-1', provider: 'netbox', name: 'Primary NetBox', base_url: 'https://netbox.example.com/api/',
      provider_details: {}, credential_configured: true, write_credential_configured: true, secret_generation: 1,
      active: true, sync_interval_minutes: 60, next_sync_at: '2026-08-12T01:00:00Z', health_status: 'healthy',
      last_successful_sync_at: null, last_error_code: '', rate_limit_reset_at: null, reconciliation_counts: {},
      created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z',
    } as IntegrationConnection
    const observation = {
      id: 'observation-1', connection_id: 'unifi-1', connection_name: 'Client UniFi', remote_type: 'unifi.network',
      remote_id: 'network-1', safe_projection: { name: 'Users', cidr: '10.42.0.0/24' }, source_timestamp: null,
      state: 'observed' as const, observed_at: '2026-08-12T00:00:00Z', linked_local_entity_id: 'network-1',
    }
    const proposal = {
      source_observation_id: observation.id, source_type: observation.remote_type, connection_id: connection.id,
      action: 'update' as const, endpoint: 'ipam/prefixes/41/', fields: { prefix: '10.42.0.0/24' },
      target_fingerprint: 'a'.repeat(64), proposal_digest: 'b'.repeat(64),
    }
    vi.mocked(provider.listConnections).mockResolvedValue([connection])
    vi.mocked(provider.listObservations).mockResolvedValue({ results: [observation], page: 1, page_size: 25, count: 1, has_more: false })
    vi.mocked(provider.previewNetBoxPublication).mockResolvedValue(proposal)
    vi.mocked(provider.publishNetBoxProposal).mockResolvedValue({ status: 'published', target_id: 41, proposal_digest: proposal.proposal_digest })
    const user = userEvent.setup()

    setup(provider, documentsClient(), '/workspaces/organizations/client-1/integrations?section=source')
    await user.click(await screen.findByRole('button', { name: 'Review for NetBox' }))
    expect(await screen.findByRole('alertdialog')).toHaveTextContent('ipam/prefixes/41/')
    expect(screen.getByRole('alertdialog')).toHaveTextContent('10.42.0.0/24')
    await user.click(screen.getByRole('button', { name: 'Publish to NetBox' }))

    await waitFor(() => expect(provider.publishNetBoxProposal).toHaveBeenCalledWith(workspace, proposal))
  })

  it('does not offer legacy NetBox record families for linking or creation', async () => {
    const provider = providerClient()
    const conflict: IntegrationConflict = {
      id: 'conflict-rack', connection_id: 'connection-1', connection_name: 'Primary NetBox', connection_provider: 'netbox',
      local_entity_id: null, provider_values: { name: 'Rack 1' }, remote_type: 'dcim.rack', remote_id: '42', difference: 'unmatched',
      status: 'open', created_at: '2026-08-12T00:00:00Z', resolved_at: null,
    }
    vi.mocked(provider.listConflicts).mockResolvedValue({ results: [conflict], page: 1, page_size: 25, count: 1, has_more: false })

    setup(provider, documentsClient(), '/workspaces/organizations/client-1/integrations?section=reconciliation')
    expect(await screen.findByText('dcim.rack:42')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Link to TekDocs' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Create a TekDocs/i)).not.toBeInTheDocument()
  })

  it('edits connection details without asking for the credential again', async () => {
    const provider = providerClient()
    const connection = {
      id: 'connection-1', provider: 'netbox', name: 'Primary NetBox', base_url: 'https://netbox.example.com/',
      provider_details: {}, credential_configured: true, secret_generation: 1, active: true, sync_interval_minutes: 60,
      health_status: 'degraded', last_successful_sync_at: null, last_error_code: 'provider_http_error', rate_limit_reset_at: null,
      reconciliation_counts: {}, next_sync_at: '2026-08-12T01:00:00Z', created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z',
    } as IntegrationConnection
    vi.mocked(provider.listConnections).mockResolvedValue([connection])
    vi.mocked(provider.updateConnection).mockResolvedValue({
      ...connection, name: 'Client NetBox', base_url: 'https://netbox.example.com/api/', sync_interval_minutes: 30,
      health_status: 'unknown', last_error_code: '',
    })
    const user = userEvent.setup()
    setup(provider)

    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    await user.clear(screen.getByLabelText('Name'))
    await user.type(screen.getByLabelText('Name'), 'Client NetBox')
    await user.clear(screen.getByLabelText('API base URL'))
    await user.type(screen.getByLabelText('API base URL'), 'https://netbox.example.com/')
    await user.clear(screen.getByLabelText('Sync interval (minutes)'))
    await user.type(screen.getByLabelText('Sync interval (minutes)'), '30')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(provider.updateConnection).toHaveBeenCalledWith(workspace, connection, {
      name: 'Client NetBox', base_url: 'https://netbox.example.com/', active: true, sync_interval_minutes: 30,
    }))
    expect(await screen.findByText('https://netbox.example.com/api/')).toBeInTheDocument()
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

    setup(provider)
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
    expect(document.querySelector('input[type="password"]')).not.toBeInTheDocument()
  })

  it('reauthenticates an expired session and safely retries the retained connection draft', async () => {
    const provider = providerClient()
    const saved = {
      id: 'connection-new', provider: 'netbox', name: 'Client NetBox', base_url: 'https://netbox.example.com/api/',
      provider_details: {}, credential_configured: true, secret_generation: 1, active: true, sync_interval_minutes: 30,
      health_status: 'unknown', last_successful_sync_at: null, last_error_code: '', rate_limit_reset_at: null,
      reconciliation_counts: {}, next_sync_at: '2026-08-12T00:00:00Z', created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z',
    } as IntegrationConnection
    vi.mocked(provider.createConnection)
      .mockRejectedValueOnce(new IntegrationRequestError('Recent authentication required.', 403, 'recent_authentication_required'))
      .mockResolvedValueOnce(saved)
    const authClient = { reauthenticate: vi.fn().mockResolvedValue(undefined) }
    const user = userEvent.setup()

    setup(provider, documentsClient(), '/workspaces/organizations/client-1/integrations', authClient)
    await user.click(await screen.findByRole('button', { name: 'New connection' }))
    await user.type(screen.getByLabelText('Name'), 'Client NetBox')
    await user.type(screen.getByLabelText('API base URL'), 'https://netbox.example.com/api/')
    await user.type(screen.getByLabelText(/API token/), 'one-time-token')
    await user.clear(screen.getByLabelText('Sync interval (minutes)'))
    await user.type(screen.getByLabelText('Sync interval (minutes)'), '30')
    await user.click(screen.getByRole('button', { name: 'Save connection' }))

    expect(await screen.findByRole('heading', { name: 'Confirm this sensitive change' })).toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toHaveValue('Client NetBox')
    await user.type(screen.getByLabelText('Current password'), 'current-password')
    await user.click(screen.getByRole('button', { name: 'Confirm and save' }))

    await waitFor(() => expect(authClient.reauthenticate).toHaveBeenCalledWith('current-password'))
    await waitFor(() => expect(provider.createConnection).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('Client NetBox')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Confirm this sensitive change' })).not.toBeInTheDocument()
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
    setup(provider)

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

  it('offers the bounded UniFi connection fields from the provider contract', async () => {
    const provider = providerClient()
    vi.mocked(provider.createConnection).mockResolvedValue({
      id: 'connection-unifi', provider: 'unifi', name: 'Office UniFi',
      base_url: 'https://console.example.test/proxy/network/integration/', provider_details: {},
      credential_configured: true, secret_generation: 1, active: true, sync_interval_minutes: 15,
      health_status: 'unknown', last_successful_sync_at: null, last_error_code: '', rate_limit_reset_at: null,
      reconciliation_counts: {}, next_sync_at: '2026-09-28T00:00:00Z', created_at: '2026-09-28T00:00:00Z', updated_at: '2026-09-28T00:00:00Z',
    })
    const user = userEvent.setup()
    setup(provider)

    await user.click(await screen.findByRole('button', { name: 'New connection' }))
    await user.selectOptions(screen.getByLabelText('Provider'), 'unifi')
    expect(screen.getByRole('link', { name: 'UniFi Network setup guidance' })).toHaveAttribute('href', 'https://help.ui.com/')
    await user.type(screen.getByLabelText('Name'), 'Office UniFi')
    await user.type(screen.getByLabelText('API base URL'), 'https://console.example.test')
    await user.type(screen.getByLabelText('API key'), 'unifi-read-key')
    await user.clear(screen.getByLabelText('Sync interval (minutes)'))
    await user.type(screen.getByLabelText('Sync interval (minutes)'), '15')
    await user.click(screen.getByRole('button', { name: 'Save connection' }))

    await waitFor(() => expect(provider.createConnection).toHaveBeenCalledWith(workspace, {
      provider: 'unifi', name: 'Office UniFi', base_url: 'https://console.example.test',
      credentials: { api_key: 'unifi-read-key' }, sync_interval_minutes: 15,
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
    setup(provider)

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

  it('uses a monitoring-only NinjaOne application and the selected regional API root', async () => {
    const provider = providerClient()
    vi.mocked(provider.createConnection).mockResolvedValue({
      id: 'connection-ninja', provider: 'ninjaone', name: 'Primary NinjaOne',
      base_url: 'https://eu.ninjarmm.com/', provider_details: { client_id: 'tekdocs-monitoring-reader' },
      credential_configured: true, secret_generation: 1, active: true, sync_interval_minutes: 15,
      health_status: 'unknown', last_successful_sync_at: null, last_error_code: '', rate_limit_reset_at: null,
      reconciliation_counts: {}, next_sync_at: '2026-08-12T00:00:00Z', created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z',
    })
    const user = userEvent.setup()
    setup(provider)

    await user.click(await screen.findByRole('button', { name: 'New connection' }))
    await user.selectOptions(screen.getByLabelText('Provider'), 'ninjaone')
    expect(screen.getByRole('link', { name: 'NinjaOne setup guidance' })).toHaveAttribute('href', expect.stringContaining('ninjaone.com/docs/'))
    await user.type(screen.getByLabelText('Name'), 'Primary NinjaOne')
    await user.clear(screen.getByLabelText('API base URL'))
    await user.type(screen.getByLabelText('API base URL'), 'https://eu.ninjarmm.com/')
    await user.type(screen.getByLabelText('API application client ID'), 'tekdocs-monitoring-reader')
    await user.type(screen.getByLabelText('API application client secret'), 'ninja-secret-value')
    await user.click(screen.getByRole('button', { name: 'Save connection' }))

    await waitFor(() => expect(provider.createConnection).toHaveBeenCalledWith(workspace, {
      provider: 'ninjaone', name: 'Primary NinjaOne', base_url: 'https://eu.ninjarmm.com/',
      credentials: { client_id: 'tekdocs-monitoring-reader', client_secret: 'ninja-secret-value' },
      sync_interval_minutes: 15,
    }))
  })

  it('separates observed, linked, accepted, review, and stale provider states', async () => {
    const provider = providerClient()
    const reviewConflict: IntegrationConflict = { id: 'conflict-3', connection_id: 'ninja', connection_name: 'NinjaOne', local_entity_id: 'asset-3', local_entity_name: 'Candidate laptop', remote_type: 'device', remote_id: '3', difference: 'changed', status: 'open', created_at: '2026-08-12T00:00:00Z', resolved_at: null }
    vi.mocked(provider.listObservations).mockResolvedValue({
      results: [
        { id: 'observed', connection_id: 'ninja', connection_name: 'NinjaOne', remote_type: 'device', remote_id: '1', safe_projection: { name: 'Observed device' }, source_timestamp: null, state: 'observed', observed_at: '2026-08-12T00:00:00Z', linked_local_entity_id: null, accepted: false, stale: false },
        { id: 'linked', connection_id: 'ninja', connection_name: 'NinjaOne', remote_type: 'health', remote_id: '2', safe_projection: { healthStatus: 'Good' }, source_timestamp: null, state: 'observed', observed_at: '2026-08-12T00:00:00Z', linked_local_entity_id: 'asset-2', linked_local_entity_name: 'Reception laptop', accepted: false, stale: false },
        { id: 'accepted', connection_id: 'ninja', connection_name: 'NinjaOne', remote_type: 'software', remote_id: '2:agent', safe_projection: { name: 'Agent' }, source_timestamp: null, state: 'observed', observed_at: '2026-08-12T00:00:00Z', linked_local_entity_id: 'software-2', linked_local_entity_name: 'Agent install', accepted: true, stale: false },
        { id: 'review', connection_id: 'ninja', connection_name: 'NinjaOne', remote_type: 'device', remote_id: '3', safe_projection: { name: 'Candidate device' }, source_timestamp: null, state: 'observed', observed_at: '2026-08-12T00:00:00Z', linked_local_entity_id: null, accepted: false, stale: true, open_conflict: reviewConflict },
      ], page: 1, page_size: 50, count: 4, has_more: false,
    })

    setup(provider)

    expect(await screen.findByText('Observed only')).toBeInTheDocument()
    expect(screen.getByText('Linked observation')).toBeInTheDocument()
    expect(screen.getByText('Accepted')).toBeInTheDocument()
    expect(screen.getByText('Needs review')).toBeInTheDocument()
    expect(screen.getByText('Reception laptop')).toBeInTheDocument()
    expect(screen.getByText('Candidate laptop')).toBeInTheDocument()
    expect(screen.getByText(/Stale · source observed/)).toBeInTheDocument()
  })
})
