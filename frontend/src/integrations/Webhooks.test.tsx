import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { WorkspaceContext } from '../workspaces/api'
import type { WebhooksClient } from './api'
import { Webhooks } from './Webhooks'

const workspace: WorkspaceContext = {
  kind: 'organization', id: 'client-1', name: 'Acme Dental', classifications: ['client'],
  capabilities: ['overview', 'integrations'], organization: null,
}

function mockClient(): WebhooksClient {
  return {
    listEndpoints: vi.fn().mockResolvedValue([{ id: 'endpoint-1', direction: 'outbound', name: 'PSA', url: 'https://hooks.example.com/tekdocs', inbound_path: null, topics: ['document_publication.available'], secret_prefix: 'tdwhsec_sample', secret_generation: 1, active: true, created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z' }]),
    createEndpoint: vi.fn(), setActive: vi.fn(), rotate: vi.fn(),
    listDeliveries: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 25, count: 0, has_more: false }),
    retry: vi.fn(),
  }
}

describe('Webhooks', () => {
  it('shows organization-scoped endpoint metadata without a stored secret', async () => {
    render(<Webhooks workspace={workspace} client={mockClient()} />)
    expect(await screen.findByText('PSA')).toBeInTheDocument()
    expect(screen.getByText('https://hooks.example.com/tekdocs')).toBeInTheDocument()
    expect(screen.queryByText(/signing secret now/i)).not.toBeInTheDocument()
    expect(screen.getByText(/No outbound deliveries/i)).toBeInTheDocument()
  })

  it('creates an inbound endpoint and presents its signing secret once', async () => {
    const createEndpoint = vi.fn()
    const client: WebhooksClient = { ...mockClient(), createEndpoint }
    createEndpoint.mockResolvedValue({ id: 'endpoint-2', direction: 'inbound', name: 'Inbound monitor', url: '', inbound_path: '/api/v1/webhooks/inbound/endpoint-2', topics: ['integration.ping'], secret_prefix: 'tdwhsec_once', secret_generation: 1, active: true, created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z', signing_secret: 'tdwhsec_one-time-secret' })
    const user = userEvent.setup()
    render(<Webhooks workspace={workspace} client={client} />)
    await screen.findByText('PSA')
    await user.click(screen.getByRole('button', { name: /new endpoint/i }))
    await user.type(screen.getByLabelText('Name'), 'Inbound monitor')
    await user.selectOptions(screen.getByLabelText('Direction'), 'inbound')
    await user.click(screen.getByRole('button', { name: /create endpoint/i }))
    await waitFor(() => expect(createEndpoint).toHaveBeenCalledWith(workspace, expect.objectContaining({ direction: 'inbound', topics: ['integration.ping'] })))
    expect(await screen.findByText('tdwhsec_one-time-secret')).toBeInTheDocument()
  })

  it('deactivates an endpoint and filters delivery inspection', async () => {
    const setActive = vi.fn().mockResolvedValue({ id: 'endpoint-1', direction: 'outbound', name: 'PSA', url: 'https://hooks.example.com/tekdocs', inbound_path: null, topics: ['document_publication.available'], secret_prefix: 'tdwhsec_sample', secret_generation: 1, active: false, created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z' })
    const listDeliveries = vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 25, count: 0, has_more: false })
    const client: WebhooksClient = { ...mockClient(), setActive, listDeliveries }
    const user = userEvent.setup()
    render(<Webhooks workspace={workspace} client={client} />)
    await user.click(await screen.findByRole('button', { name: 'Deactivate' }))
    await waitFor(() => expect(setActive).toHaveBeenCalledWith(workspace, expect.objectContaining({ id: 'endpoint-1' }), false))
    expect(await screen.findByText('Inactive')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^Filters$/ }))
    await user.click(screen.getByText('State', { exact: true }))
    await user.click(screen.getByRole('radio', { name: 'Dead letter' }))
    await waitFor(() => expect(listDeliveries).toHaveBeenLastCalledWith(workspace, 1, 'dead_letter', expect.any(AbortSignal)))
  })
})
