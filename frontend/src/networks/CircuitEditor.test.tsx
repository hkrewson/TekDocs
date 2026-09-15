import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import type { WorkspaceContext } from '../workspaces/api'
import type { CircuitChoiceQuery, CircuitDetail, NetworksClient } from './api'
import { CircuitEditor } from './CircuitEditor'
const workspace = { kind: 'msp', id: 'msp' } as WorkspaceContext
function setup(record: CircuitDetail | null = null, fail = false) {
  const onSaved = vi.fn(), onCancel = vi.fn()
  const create = fail ? vi.fn().mockRejectedValue(new Error('Denied. Your entries have been kept.')) : vi.fn().mockResolvedValue({ id: 'saved' })
  const update = vi.fn().mockResolvedValue({ id: 'saved' })
  const choices = vi.fn().mockImplementation((_workspace: WorkspaceContext, query: CircuitChoiceQuery) => Promise.resolve({ results: query.q ? [] : [{ id: query.choice === 'providers' ? 'carrier' : 'agreement', name: query.choice === 'providers' ? 'Carrier' : 'Agreement' }], selected: query.selected_id ? { id: query.selected_id, name: 'Retained' } : null, count: query.q ? 0 : 1, page: query.page, page_size: 25, has_more: false, can_view_contracts: true }))
  const client = { circuitChoicePage: choices, createCircuit: create, updateCircuit: update } as unknown as NetworksClient
  window.history.replaceState({}, '', '/networks?view=circuits&circuits=new')
  render(<ApplicationRouter><CircuitEditor record={record} workspace={workspace} client={client} canManage onSaved={onSaved} onReturn={onCancel} onCancel={onCancel} /></ApplicationRouter>)
  return { user: userEvent.setup(), create, update, choices, onSaved, onCancel }
}
it('creates an ordered service with bounded choices and retains its provider outside search', async () => {
  const { user, create, choices, onSaved } = setup()
  await user.type(screen.getByRole('textbox', { name: 'Name' }), 'New circuit')
  await user.type(screen.getByRole('textbox', { name: 'Service identifier' }), 'NEW-1')
  await user.selectOptions(await screen.findByRole('combobox', { name: 'Provider' }), 'carrier')
  await user.type(screen.getByRole('searchbox', { name: 'Search providers' }), 'missing')
  fireEvent.keyDown(screen.getByRole('searchbox', { name: 'Search providers' }), { key: 'Enter' })
  await waitFor(() => expect(choices).toHaveBeenCalledWith(workspace, expect.objectContaining({ q: 'missing', selected_id: 'carrier', page_size: 25 }), expect.any(AbortSignal)))
  expect(screen.getByText('Carrier')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Add circuit' }))
  await waitFor(() => expect(create).toHaveBeenCalledWith(workspace, expect.objectContaining({ name: 'New circuit', service_identifier: 'NEW-1', provider_id: 'carrier', contract_id: null, status: 'ordered' })))
  expect(onSaved).toHaveBeenCalled()
})
it('keeps failed creation values and selected provider without retry', async () => {
  const { user, create } = setup(null, true)
  await user.type(screen.getByRole('textbox', { name: 'Name' }), 'Draft')
  await user.type(screen.getByRole('textbox', { name: 'Service identifier' }), 'DRAFT')
  await user.selectOptions(await screen.findByRole('combobox', { name: 'Provider' }), 'carrier')
  await user.click(screen.getByRole('button', { name: 'Add circuit' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Denied')
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('Draft')
  expect(create).toHaveBeenCalledTimes(1)
})
it('assigns a contract without resubmitting provider or service fields', async () => {
  const { user, update } = setup({ id: 'circuit', provider_id: 'carrier', provider_name: 'Carrier', contract: null } as CircuitDetail)
  await user.selectOptions(await screen.findByRole('combobox', { name: 'Contract' }), 'agreement')
  await user.click(screen.getByRole('button', { name: 'Save provider and contract' }))
  await waitFor(() => expect(update).toHaveBeenCalledWith(workspace, 'circuit', { contract_id: 'agreement' }))
})
it('protects a restricted contract projection without loading assignment choices', () => {
  const { choices } = setup({ id: 'circuit', provider_id: 'carrier', provider_name: 'Carrier' } as CircuitDetail)
  expect(screen.getByText('Provider and contract changes require access to contracts.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Save provider and contract' })).toBeDisabled()
  expect(choices).not.toHaveBeenCalled()
})
