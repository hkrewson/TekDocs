import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { browserOperationsClient } from '../operations/api'
import { AuthRequestError } from '../auth/api'
afterEach(() => vi.restoreAllMocks())
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { defaultPreferences } from '../collections/preferences'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworksClient } from './api'
import { DNSRegister } from './DNSRegister'
const workspace = { kind: 'msp', id: 'msp', name: 'MSP' } as WorkspaceContext
function setup({ denied = false, fail = false, mismatch = false, initial = '', historyDenied = false, zoneName = 'example.invalid' } = {}) {
  const activity = vi.spyOn(browserOperationsClient, 'activity')
  if (historyDenied) activity.mockRejectedValue(new AuthRequestError('Not allowed', 403))
  else activity.mockResolvedValue({ results: [], count: 31, page: 1, page_size: 25, has_more: true, actions: [] })
  window.history.replaceState({}, '', `/networks?view=dns${initial}`)
  const zone = { id: 'zone-1', name: zoneName, description: 'Zone notes', record_count: 31 }
  const record = { id: 'record-1', zone_id: mismatch ? 'another-zone' : zone.id, zone_name: zone.name, owner_name: 'host.example.invalid', record_type: 'TXT', value: 'Documented value', ttl: 3600, priority: null, weight: null, port: null, ip_address_id: null, description: 'Record notes' }
  const result = { page: 1, page_size: 25, count: 31, has_more: true, can_manage: !denied }
  const write = fail ? vi.fn().mockRejectedValue(new Error('Record changed.')) : vi.fn().mockResolvedValue(record)
  const dnsRecordCollection = vi.fn().mockResolvedValue({ ...result, results: [record] })
  const createDNSZone = vi.fn().mockResolvedValue(zone)
  const client = { dnsZoneCollection: vi.fn().mockResolvedValue({ ...result, results: [zone] }), dnsZoneDetail: vi.fn().mockResolvedValue(zone), dnsRecordCollection, dnsRecordDetail: vi.fn().mockResolvedValue(record), updateDNSZone: vi.fn().mockResolvedValue(zone), createDNSZone, updateDNSRecord: write, createDNSRecord: write, addressCollection: vi.fn().mockResolvedValue({ ...result, results: [] }) } as unknown as NetworksClient
  const preferenceClient = { load: vi.fn().mockImplementation((_workspace, feature) => Promise.resolve(defaultPreferences(feature === 'dns-zones' ? ['name', 'record_count'] : ['name', 'record_type', 'value', 'ttl']))), save: vi.fn(), reset: vi.fn() }
  // Child preferences use the browser client; fallback defaults must remain usable.
  render(<ApplicationRouter><DNSRegister workspace={workspace} client={client} preferenceClient={preferenceClient} /></ApplicationRouter>)
  return { activity, createDNSZone, dnsRecordCollection, client, write, user: userEvent.setup() }
}
it('loads records only on demand and scopes search to the selected zone', async () => {
  const { dnsRecordCollection, user } = setup()
  await user.click(await screen.findByRole('button', { name: 'example.invalid' }))
  expect(dnsRecordCollection).not.toHaveBeenCalled()
  const drawer = await screen.findByRole('dialog', { name: 'example.invalid' })
  await user.click(within(drawer).getByRole('link', { name: 'Records' }))
  await user.type(await within(drawer).findByRole('searchbox'), 'host')
  await user.click(within(drawer).getByRole('button', { name: 'Search' }))
  await waitFor(() => expect(dnsRecordCollection).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ zone_id: 'zone-1', q: 'host', page: 1, page_size: 25 }), expect.any(AbortSignal)))
  await user.click(await within(drawer).findByRole('button', { name: 'host.example.invalid' }))
  expect(await within(drawer).findByText('Record notes')).toBeVisible()
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
  await user.click(within(drawer).getByRole('button', { name: 'Back to DNS records' }))
  expect(await within(drawer).findByRole('button', { name: 'host.example.invalid' })).toHaveFocus()
})
it('keeps a failed record edit and guards dismissal without retrying', async () => {
  const { user, write } = setup({ fail: true, initial: '&dns=zone-1&dns_section=records&dns_record=record-1' })
  const drawer = await screen.findByRole('dialog', { name: 'example.invalid' })
  await user.click(await within(drawer).findByRole('button', { name: 'Edit DNS record' }))
  await user.type(within(drawer).getByLabelText('Value'), ' changed')
  await user.click(within(drawer).getByRole('button', { name: 'Save DNS record' }))
  expect(await within(drawer).findByRole('alert')).toHaveTextContent('Record changed')
  expect(write.mock.calls[0]?.[2]).not.toHaveProperty('zone_id')
  fireEvent(drawer, new Event('cancel', { cancelable: true }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(within(drawer).getByLabelText('Value')).toHaveValue('Documented value changed')
  expect(write).toHaveBeenCalledTimes(1)
})
it('rejects a direct child link from another zone', async () => {
  setup({ mismatch: true, initial: '&dns=zone-1&dns_section=records&dns_record=record-1' })
  expect(await screen.findByRole('alert')).toHaveTextContent('unavailable')
  expect(screen.queryByText('Record notes')).not.toBeInTheDocument()
})
it('omits creation and edit controls for read-only members', async () => {
  setup({ denied: true, initial: '&dns=zone-1&dns_section=records&dns_record=record-1' })
  expect(await screen.findByText('Record notes')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Edit DNS record' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Add zone' })).not.toBeInTheDocument()
})
it('creates an SRV child with the fixed parent and preserves zero priority and weight', async () => {
  const { user, write } = setup({ initial: '&dns=zone-1&dns_section=records&dns_record=new' })
  const drawer = await screen.findByRole('dialog', { name: 'example.invalid' })
  await user.type(await within(drawer).findByLabelText('Owner name'), '_sip._tcp.example.invalid')
  await user.selectOptions(within(drawer).getByLabelText('Type'), 'SRV')
  await user.type(within(drawer).getByLabelText('Value'), 'voice.example.invalid')
  await user.type(within(drawer).getByLabelText('Priority'), '0')
  await user.type(within(drawer).getByLabelText('Weight'), '0')
  await user.type(within(drawer).getByLabelText('Port'), '5060')
  await user.click(within(drawer).getByRole('button', { name: 'Save DNS record' }))
  expect(write).toHaveBeenCalledWith(workspace, expect.objectContaining({ zone_id: 'zone-1', owner_name: '_sip._tcp.example.invalid', record_type: 'SRV', priority: 0, weight: 0, port: 5060 }))
})
it('guards a new record when returning to its collection', async () => {
  const { user, write } = setup({ initial: '&dns=zone-1&dns_section=records&dns_record=new' })
  const drawer = await screen.findByRole('dialog', { name: 'example.invalid' })
  await user.type(await within(drawer).findByLabelText('Owner name'), 'unsaved.example.invalid')
  await user.click(within(drawer).getByRole('button', { name: 'Back to DNS records' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(within(drawer).getByLabelText('Owner name')).toHaveValue('unsaved.example.invalid')
  expect(write).not.toHaveBeenCalled()
})

it('creates a zone through the focused drawer and guards unsaved tab changes', async () => {
  const { user, createDNSZone } = setup({ initial: '&dns=new' })
  await user.type(await screen.findByLabelText('Zone name'), 'example.invalid')
  await user.type(screen.getByLabelText('Description'), 'Zone notes')
  await user.click(screen.getByRole('button', { name: 'Save zone' }))
  await screen.findByRole('dialog', { name: 'example.invalid' })
  expect(createDNSZone).toHaveBeenCalledWith(workspace, { name: 'example.invalid', description: 'Zone notes' })
  await user.click(screen.getByRole('button', { name: 'Edit zone' }))
  await user.type(screen.getByLabelText('Description'), ' unsaved')
  await user.click(screen.getByRole('link', { name: 'Records' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(screen.getByLabelText('Description')).toHaveValue('Zone notes unsaved')
})

it('loads only the selected DNS record history on demand and keeps its page separate from zone history', async () => {
  const { user, activity } = setup({ initial: '&dns=zone-1&dns_section=records&dns_record=record-1&history_page=3' })
  const drawer = await screen.findByRole('dialog', { name: 'example.invalid' })
  await within(drawer).findByText('Record notes')
  expect(activity).not.toHaveBeenCalled()
  expect(within(drawer).getByRole('heading', { name: 'host.example.invalid' })).toHaveFocus()
  await user.click(within(drawer).getByRole('link', { name: 'View record history' }))
  expect(await within(drawer).findByText('No DNS record history is available.')).toBeVisible()
  expect(activity).toHaveBeenLastCalledWith({}, { entity_id: 'record-1', page: 1, page_size: 25 }, expect.any(AbortSignal))
  await user.click(within(drawer).getByRole('button', { name: 'Next' }))
  await waitFor(() => expect(activity).toHaveBeenLastCalledWith({}, { entity_id: 'record-1', page: 2, page_size: 25 }, expect.any(AbortSignal)))
  expect(new URLSearchParams(window.location.search).get('history_page')).toBe('3')
  expect(new URLSearchParams(window.location.search).get('dns_record_history_page')).toBe('2')
  await user.click(within(drawer).getByRole('link', { name: 'Back to record details' }))
  expect(await within(drawer).findByText('Record notes')).toBeVisible()
  await user.click(within(drawer).getByRole('button', { name: 'Back to DNS records' }))
  expect(new URLSearchParams(window.location.search).has('dns_record_history_page')).toBe(false)
})
it('guards record history navigation after a failed save', async () => {
  const { user, activity } = setup({ fail: true, initial: '&dns=zone-1&dns_section=records&dns_record=record-1' })
  const drawer = await screen.findByRole('dialog', { name: 'example.invalid' })
  await user.click(await within(drawer).findByRole('button', { name: 'Edit DNS record' }))
  await user.type(within(drawer).getByLabelText('Value'), ' changed')
  await user.click(within(drawer).getByRole('button', { name: 'Save DNS record' }))
  await within(drawer).findByRole('alert')
  await user.click(within(drawer).getByRole('link', { name: 'View record history' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(within(drawer).getByLabelText('Value')).toHaveValue('Documented value changed')
  expect(activity).not.toHaveBeenCalled()
})
it('shows denied history without hiding the record or its return path', async () => {
  const { user, activity } = setup({ historyDenied: true, initial: '&dns=zone-1&dns_section=records&dns_record=record-1&dns_record_view=history' })
  const drawer = await screen.findByRole('dialog', { name: 'example.invalid' })
  expect(await within(drawer).findByRole('alert')).toHaveTextContent('You cannot view DNS record history.')
  expect(activity).toHaveBeenCalledTimes(1)
  await user.click(within(drawer).getByRole('link', { name: 'Back to record details' }))
  expect(await within(drawer).findByText('Record notes')).toBeVisible()
})
it('never requests history for a child linked from a different zone', async () => {
  const { activity } = setup({ mismatch: true, initial: '&dns=zone-1&dns_section=records&dns_record=record-1&dns_record_view=history' })
  expect(await screen.findByRole('alert')).toHaveTextContent('unavailable')
  expect(activity).not.toHaveBeenCalled()
})

it('exposes the complete zone name in Overview for read-only members', async () => {
  const zoneName = `${'a'.repeat(60)}.${'b'.repeat(60)}.${'c'.repeat(60)}.example.invalid`
  setup({ denied: true, initial: '&dns=zone-1', zoneName })
  const drawer = await screen.findByRole('dialog', { name: zoneName })
  expect(within(drawer).getByText('Zone', { selector: 'dt' })).toBeVisible()
  expect(within(drawer).getByText(zoneName, { selector: 'dd' })).toBeVisible()
  expect(within(drawer).queryByRole('button', { name: 'Edit zone' })).not.toBeInTheDocument()
})
