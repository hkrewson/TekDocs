/* eslint-disable @typescript-eslint/unbound-method */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { DataFlows } from './DataFlows'
import type { DataFlow, DataFlowChoices, DataFlowClient, DataFlowRevision } from './dataFlowApi'

const choices: DataFlowChoices = {
  endpoint_kinds: [{ value: 'internal', label: 'Internal record' }, { value: 'external', label: 'External party' }],
  directions: [{ value: 'one_way', label: 'One way' }, { value: 'bidirectional', label: 'Bidirectional' }],
  transfer_mechanisms: [{ value: 'api', label: 'API' }, { value: 'email', label: 'Email' }],
  data_classifications: [{ value: 'internal', label: 'Internal' }, { value: 'personal_data', label: 'Personal data' }],
  protections: [{ value: 'unknown', label: 'Unknown' }, { value: 'in_transit', label: 'Encrypted in transit' }],
  provenance_states: [
    { value: 'recorded_fact', label: 'Recorded fact' },
    { value: 'imported_observation', label: 'Imported observation' },
    { value: 'unverified_draft', label: 'Unverified draft' },
  ],
}

function revision(overrides: Partial<DataFlowRevision> = {}): DataFlowRevision {
  return {
    id: 'revision-1', revision_number: 1,
    source_kind: 'external', source_entity_id: null, source_display_name: 'Practice vendor', source_label: 'Practice vendor',
    destination_kind: 'external', destination_entity_id: null, destination_display_name: 'Processor', destination_label: 'Processor',
    direction: 'one_way', transfer_mechanism: 'api', data_classification: 'personal_data',
    purpose: 'Settle patient billing.', crosses_trust_boundary: true, protection: 'in_transit',
    owner_entity_id: null, owner_display_name: '', review_due_on: null, provenance: 'recorded_fact',
    content_digest: 'a'.repeat(64), created_at: '2026-08-20T12:00:00Z',
    ...overrides,
  }
}

function flow(overrides: Partial<DataFlow> = {}): DataFlow {
  return {
    id: 'flow-1', name: 'Billing export', revision_count: 1, current_revision: revision(),
    created_at: '2026-08-20T12:00:00Z', updated_at: '2026-08-20T12:00:00Z',
    ...overrides,
  }
}

function client(overrides: Partial<DataFlowClient> = {}, records: DataFlow[] = [flow()], canManage = true): DataFlowClient {
  return {
    list: vi.fn().mockResolvedValue({ results: records, page: 1, page_size: 50, count: records.length, has_more: false, can_manage: canManage }),
    choices: vi.fn().mockResolvedValue(choices),
    revisions: vi.fn().mockResolvedValue({ results: [revision({ revision_number: 2, provenance: 'unverified_draft' }), revision()], count: 2 }),
    create: vi.fn().mockResolvedValue(flow()),
    revise: vi.fn().mockResolvedValue(flow()),
    archive: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

it('lists a flow with the parties it moves data between and its asserted protection', async () => {
  render(<DataFlows workspace={null} client={client()} />)

  const table = await screen.findByRole('group', { name: 'Data flows' })
  expect(within(table).getByText('Billing export')).toBeVisible()
  expect(within(table).getByText('Practice vendor → Processor')).toBeVisible()
  expect(within(table).getByText('Personal data')).toBeVisible()
  expect(within(table).getByText('Encrypted in transit')).toBeVisible()
  expect(within(table).getByText('Crosses a trust boundary')).toBeVisible()
})

it('never lets an unverified draft read as evidence', async () => {
  const drafted = flow({ current_revision: revision({ provenance: 'unverified_draft' }) })
  render(<DataFlows workspace={null} client={client({}, [drafted])} />)

  // The distinction must survive greyscale and a screen reader, so the words carry it
  // rather than the pill colour.
  const pill = await screen.findByText(/Unverified draft/)
  expect(pill).toHaveTextContent('not evidence')
  expect(pill.className).toContain('unverified_draft')
})

it('states a recorded fact without the draft qualifier', async () => {
  render(<DataFlows workspace={null} client={client()} />)

  const pill = await screen.findByText('Recorded fact')
  expect(pill).not.toHaveTextContent('not evidence')
})

it('declares a flow from the vocabulary the server served', async () => {
  const user = userEvent.setup()
  const api = client()
  render(<DataFlows workspace={null} client={api} />)
  await user.click(await screen.findByRole('button', { name: 'Declare data flow' }))

  await user.type(screen.getByLabelText('Name'), 'Backup replication')
  await user.type(screen.getByLabelText('Purpose'), 'Offsite retention.')
  await user.type(screen.getByLabelText('Source'), 'Primary server')
  await user.type(screen.getByLabelText('Destination'), 'Offsite vault')
  await user.selectOptions(screen.getByLabelText('Provenance'), 'recorded_fact')
  await user.click(screen.getByRole('button', { name: 'Save data flow' }))

  await waitFor(() => expect(api.create).toHaveBeenCalledWith(null, expect.objectContaining({
    name: 'Backup replication', source_label: 'Primary server', destination_label: 'Offsite vault',
    provenance: 'recorded_fact', source_kind: 'external', destination_kind: 'external',
  })))
})

it('revises an existing flow from its current revision rather than a blank form', async () => {
  const user = userEvent.setup()
  const api = client()
  render(<DataFlows workspace={null} client={api} />)
  await user.click(await screen.findByRole('button', { name: 'Edit' }))

  expect(screen.getByLabelText<HTMLInputElement>('Purpose').value).toBe('Settle patient billing.')
  await user.selectOptions(screen.getByLabelText('Protection'), 'unknown')
  await user.click(screen.getByRole('button', { name: 'Save revision' }))

  await waitFor(() => expect(api.revise).toHaveBeenCalledWith(null, 'flow-1', expect.objectContaining({ protection: 'unknown' })))
})

it('shows every retained revision with the provenance each one asserted', async () => {
  const user = userEvent.setup()
  render(<DataFlows workspace={null} client={client()} />)
  await user.click(await screen.findByRole('button', { name: 'History' }))

  const history = await screen.findByRole('group', { name: 'Data flow revisions' })
  expect(within(history).getByText(/Unverified draft/)).toBeVisible()
  expect(within(history).getByText('Recorded fact')).toBeVisible()
})

it('offers no authoring controls to a member who may only read', async () => {
  render(<DataFlows workspace={null} client={client({}, [flow()], false)} />)

  await screen.findByText('Billing export')
  expect(screen.queryByRole('button', { name: 'Declare data flow' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument()
})

it('repeats the reason the server refused a flow', async () => {
  const user = userEvent.setup()
  const api = client({ create: vi.fn().mockRejectedValue(new Error('The selected source is unavailable in this workspace.')) })
  render(<DataFlows workspace={null} client={api} />)
  await user.click(await screen.findByRole('button', { name: 'Declare data flow' }))
  await user.type(screen.getByLabelText('Name'), 'Rejected')
  await user.type(screen.getByLabelText('Purpose'), 'Rejected.')
  await user.type(screen.getByLabelText('Source'), 'Elsewhere')
  await user.type(screen.getByLabelText('Destination'), 'Elsewhere')
  await user.click(screen.getByRole('button', { name: 'Save data flow' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('The selected source is unavailable in this workspace.')
})

it('stays out of the page entirely when the member may not read data flows', async () => {
  // Data flows carry their own permission inside the compliance area, so a refusal is
  // not a broken page — the section simply does not apply.
  const api = client({ list: vi.fn().mockRejectedValue(new Error('forbidden')) })
  const { container } = render(<DataFlows workspace={null} client={api} />)

  await waitFor(() => expect(container).toBeEmptyDOMElement())
})
