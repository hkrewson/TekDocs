import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Contracts } from './Contracts'
import type { CommercialClient, CommercialContract } from './api'

const workspace = { id: 'client-1', name: 'Contoso', classifications: ['client'] } as never
const contract: CommercialContract = {
  id: 'contract-1', name: 'Managed endpoint service', provider_id: 'provider-1', provider_name: 'Northwind',
  kind: 'service', status: 'active', description: 'Monitoring and response', reference: 'MSA-204',
  starts_on: '2026-08-01', ends_on: '2027-07-31', renews_on: '2027-07-01', auto_renew: true,
  renewal_notice_days: 30, costs: [],
}

function commercialClient(overrides: Partial<CommercialClient> = {}): CommercialClient {
  return {
    listContracts: vi.fn().mockResolvedValue({ results: [contract], count: 1, can_manage: true, can_view_costs: true }),
    providerChoices: vi.fn().mockResolvedValue({ results: [{ id: 'provider-1', name: 'Northwind' }] }),
    createContract: vi.fn().mockResolvedValue(contract), updateContract: vi.fn().mockResolvedValue(contract),
    archiveContract: vi.fn().mockResolvedValue(undefined),
    createCost: vi.fn().mockResolvedValue({ ...contract, costs: [{ id: 'cost-1', label: 'Managed devices', amount: '19.50', currency: 'USD', billing_interval: 'monthly', quantity: '25.000', starts_on: null, ends_on: null, reference: '' }] }),
    updateCost: vi.fn().mockResolvedValue(contract), archiveCost: vi.fn().mockResolvedValue(contract),
    ...overrides,
  }
}

describe('Contracts', () => {
  it('creates a provider contract and a permission-controlled cost', async () => {
    const createContract = vi.fn().mockResolvedValue(contract)
    const createCost = vi.fn().mockResolvedValue({ ...contract, costs: [{ id: 'cost-1', label: 'Managed devices', amount: '19.50', currency: 'USD', billing_interval: 'monthly', quantity: '25.000', starts_on: null, ends_on: null, reference: '' }] })
    const updateCost = vi.fn().mockResolvedValue({ ...contract, costs: [{ id: 'cost-1', label: 'Managed devices', amount: '21.00', currency: 'USD', billing_interval: 'monthly', quantity: '25.000', starts_on: null, ends_on: null, reference: '' }] })
    const user = userEvent.setup()
    render(<Contracts workspace={workspace} client={commercialClient({ createContract, createCost, updateCost })} />)
    await user.click(await screen.findByRole('button', { name: 'New contract' }))
    const form = screen.getByRole('dialog')
    await user.type(within(form).getByLabelText('Contract name'), 'Managed endpoint service')
    await user.selectOptions(within(form).getByLabelText('Provider'), 'provider-1')
    await user.click(within(form).getByRole('button', { name: 'Save contract' }))
    await waitFor(() => expect(createContract).toHaveBeenCalledWith(workspace, expect.objectContaining({ name: 'Managed endpoint service', provider_id: 'provider-1' })))

    await user.click(screen.getByRole('button', { name: 'Add cost' }))
    const costForm = screen.getByRole('dialog')
    await user.type(within(costForm).getByLabelText('Cost label'), 'Managed devices')
    await user.type(within(costForm).getByLabelText('Amount'), '19.50')
    await user.click(within(costForm).getByRole('button', { name: 'Add cost' }))
    await waitFor(() => expect(createCost).toHaveBeenCalledWith(workspace, 'contract-1', expect.objectContaining({ amount: '19.5', currency: 'USD' })))
    expect(await screen.findByText(/USD 19.50/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Edit cost Managed devices' }))
    const editCostForm = screen.getByRole('dialog')
    await user.clear(within(editCostForm).getByLabelText('Amount'))
    await user.type(within(editCostForm).getByLabelText('Amount'), '21.00')
    await user.click(within(editCostForm).getByRole('button', { name: 'Save cost' }))
    await waitFor(() => expect(updateCost).toHaveBeenCalledWith(workspace, 'contract-1', 'cost-1', expect.objectContaining({ amount: '21' })))
  })

  it('does not render cost controls or values when the projection is denied', async () => {
    render(<Contracts workspace={workspace} client={commercialClient({ listContracts: vi.fn().mockResolvedValue({ results: [{ ...contract, costs: undefined }], count: 1, can_manage: true, can_view_costs: false }) })} />)
    expect(await screen.findByText(/Financial terms are hidden/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add cost' })).not.toBeInTheDocument()
    expect(screen.queryByText('19.50')).not.toBeInTheDocument()
  })

  it('clears an open financial editor before switching client context', async () => {
    const costed = { ...contract, costs: [{ id: 'cost-1', label: 'Private rate', amount: '875.50', currency: 'USD', billing_interval: 'monthly' as const, quantity: '1.000', starts_on: null, ends_on: null, reference: '' }] }
    const listContracts = vi.fn().mockImplementation((activeWorkspace: { id: string }) => Promise.resolve(
      activeWorkspace.id === 'client-1'
        ? { results: [costed], count: 1, can_manage: true, can_view_costs: true }
        : { results: [], count: 0, can_manage: true, can_view_costs: false },
    ))
    const client = commercialClient({ listContracts })
    const user = userEvent.setup()
    const { rerender } = render(<Contracts key="client-1" workspace={workspace} client={client} />)
    await user.click(await screen.findByRole('button', { name: 'Edit cost Private rate' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    rerender(<Contracts key="client-2" workspace={{ id: 'client-2', name: 'Fabrikam', classifications: ['client'] } as never} client={client} />)
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.queryByDisplayValue('875.50')).not.toBeInTheDocument()
  })
})
