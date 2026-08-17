import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { RelationshipGraph as Graph, RelationshipsClient } from './api'
import { RelationshipGraph } from './RelationshipGraph'

vi.mock('cytoscape', () => ({
  default: vi.fn(() => ({ destroy: vi.fn(), fit: vi.fn(), on: vi.fn() })),
}))

const graph: Graph = {
  family: 'network',
  workspace: { kind: 'organization', id: 'org-1' },
  root_entity_id: 'network-1',
  depth: 2,
  edge_limit: 150,
  truncated: false,
  digest: 'a'.repeat(64),
  nodes: [
    { id: 'network-1', label: 'Office LAN', entity_type: 'network_subnet', visibility: 'client_visible', root: true },
    { id: 'asset-1', label: 'Firewall', entity_type: 'client_asset', visibility: 'client_visible', root: false },
  ],
  edges: [{ id: 'link-1', source: 'network-1', target: 'asset-1', link_type: 'connected_to', label: 'Connected to', symmetric: true }],
}

function client(): RelationshipsClient {
  return {
    linkTypes: vi.fn(), search: vi.fn(), list: vi.fn(), create: vi.fn(), archive: vi.fn(),
    graph: vi.fn().mockResolvedValue(graph),
  }
}

describe('RelationshipGraph', () => {
  it('renders only the authorized projection with an equivalent accessible table', async () => {
    const graphClient = client()
    render(<MemoryRouter><RelationshipGraph scope={{ organizationId: 'org-1' }} family="network" rootId="network-1" client={graphClient} /></MemoryRouter>)

    expect(await screen.findByRole('img', { name: /2 visible records and 1 relationships/i })).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Accessible relationship list' })).toHaveTextContent('Office LANConnected toFirewall')
    expect(graphClient.graph).toHaveBeenCalledWith({ organizationId: 'org-1' }, 'network', expect.objectContaining({ rootId: 'network-1', depth: 2 }), expect.any(AbortSignal))
  })
})
