import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { NavigationGuardProvider } from '../navigation/NavigationGuardProvider'
import { InvoiceRequestError } from './api'
import { InvoiceSettings } from './InvoiceSettings'

const settings = {
  configured: true, issue_ready: true, readiness_issues: [], legal_name: 'Example MSP, LLC', address_line_1: '100 Main Street',
  address_line_2: '', city: 'Austin', region: 'TX', postal_code: '78701', country_code: 'US',
  billing_email: 'billing@example.invalid', phone: '', tax_registration: '', default_currency: 'USD',
  payment_terms_days: 30, invoice_prefix: 'INV', invoice_date_component: 'none' as const, invoice_separator: '-' as const,
  invoice_sequence_digits: 6, invoice_reset_period: 'never' as const,
  country_choices: [{ value: 'CA', label: 'Canada' }, { value: 'US', label: 'United States' }],
}

describe('InvoiceSettings', () => {
  const authClient = { reauthenticate: vi.fn().mockResolvedValue(undefined) }

  function setup(client: Parameters<typeof InvoiceSettings>[0]['client'], path = '/invoices', reauthenticationClient = authClient) {
    const router = createMemoryRouter([{
      path: '*',
      element: <NavigationGuardProvider><InvoiceSettings client={client} authClient={reauthenticationClient} /></NavigationGuardProvider>,
    }], { initialEntries: [path] })
    render(<RouterProvider router={router} />)
    return router
  }

  it('opens one focused settings section instead of one competing long form', async () => {
    setup({ issueSettings: vi.fn().mockResolvedValue(settings), saveIssueSettings: vi.fn() })

    expect(await screen.findByRole('group', { name: 'Your business details' })).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Invoice defaults' })).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Invoice numbering' })).not.toBeInTheDocument()
  })

  it('edits the tenant-wide billing profile from the MSP accounting page', async () => {
    const user = userEvent.setup()
    const saveIssueSettings = vi.fn().mockResolvedValue(settings)
    setup({ issueSettings: vi.fn().mockResolvedValue(settings), saveIssueSettings })

    expect(await screen.findByRole('heading', { name: 'Invoice settings' })).toBeInTheDocument()
    expect(screen.getByText('Your business details and invoice defaults are used for every client.')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Your business details' })).toBeInTheDocument()
    expect(screen.getByLabelText('Legal business name')).toHaveFocus()
    expect(screen.getByLabelText('Country')).toHaveValue('US')
    expect(screen.getByRole('option', { name: 'United States — US' })).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Invoice numbering' }))
    expect(await screen.findByRole('group', { name: 'Invoice numbering' })).toBeInTheDocument()
    expect(screen.getByLabelText('Invoice prefix')).toHaveFocus()
    fireEvent.change(screen.getByLabelText('Invoice prefix'), { target: { value: 'MSP' } })
    fireEvent.change(screen.getByLabelText('Restart sequence'), { target: { value: 'monthly' } })
    expect(screen.getByLabelText('Date in number')).toHaveValue('year_month')
    expect(screen.getByText('MSP-202608-000001')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save invoice settings' }))

    await waitFor(() => expect(saveIssueSettings).toHaveBeenCalledWith(expect.objectContaining({ invoice_prefix: 'MSP', invoice_reset_period: 'monthly' })))
    expect(saveIssueSettings.mock.calls[0][0]).not.toHaveProperty('country_choices')
    expect(saveIssueSettings.mock.calls[0][0]).not.toHaveProperty('readiness_issues')
    expect(await screen.findByText('Invoice settings saved.')).toBeInTheDocument()
  })

  it('confirms the password and retries a save when recent authentication expired', async () => {
    const saveIssueSettings = vi.fn()
      .mockRejectedValueOnce(new InvoiceRequestError('The request is not authorized.', 403, 'recent_authentication_required'))
      .mockResolvedValueOnce(settings)
    const reauthenticate = vi.fn().mockResolvedValue(undefined)
    setup({ issueSettings: vi.fn().mockResolvedValue(settings), saveIssueSettings }, '/invoices', { reauthenticate })

    await screen.findByRole('heading', { name: 'Invoice settings' })
    fireEvent.click(screen.getByRole('button', { name: 'Save invoice settings' }))
    expect(await screen.findByRole('heading', { name: 'Confirm this change' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'current-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and save' }))

    await waitFor(() => expect(reauthenticate).toHaveBeenCalledWith('current-password'))
    await waitFor(() => expect(saveIssueSettings).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('Invoice settings saved.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Current password')).not.toBeInTheDocument()
  })

  it('keeps edited settings visible when saving fails', async () => {
    const saveIssueSettings = vi.fn().mockRejectedValue(new Error('Internal server error'))
    setup({ issueSettings: vi.fn().mockResolvedValue(settings), saveIssueSettings }, '/invoices?section=numbering')

    await screen.findByRole('heading', { name: 'Invoice settings' })
    fireEvent.change(screen.getByLabelText('Invoice prefix'), { target: { value: 'MSP' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save invoice settings' }))

    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't save invoice settings. Your changes are still here. Try again.")
    expect(screen.getByLabelText('Invoice prefix')).toHaveValue('MSP')
  })

  it('opens direct section URLs and protects unsaved settings during section navigation', async () => {
    const user = userEvent.setup()
    const router = setup({ issueSettings: vi.fn().mockResolvedValue(settings), saveIssueSettings: vi.fn() })
    await user.clear(await screen.findByLabelText('Legal business name'))
    await user.type(screen.getByLabelText('Legal business name'), 'Draft MSP')
    await user.click(screen.getByRole('link', { name: 'Invoice defaults' }))
    await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
    expect(router.state.location.search).toBe('')
    expect(screen.getByLabelText('Legal business name')).toHaveValue('Draft MSP')
    await user.click(screen.getByRole('link', { name: 'Invoice defaults' }))
    await user.click(await screen.findByRole('button', { name: 'Discard changes' }))
    await waitFor(() => expect(router.state.location.search).toBe('?section=defaults'))
    expect(screen.getByRole('group', { name: 'Invoice defaults' })).toBeInTheDocument()
    expect(screen.getByLabelText('Default currency')).toHaveFocus()
  })

  it('retries settings that fail to load', async () => {
    const issueSettings = vi.fn().mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValueOnce(settings)
    setup({ issueSettings, saveIssueSettings: vi.fn() })
    expect(await screen.findByRole('heading', { name: "Couldn't load invoice settings." })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('group', { name: 'Your business details' })).toBeInTheDocument()
    expect(issueSettings).toHaveBeenCalledTimes(2)
  })
})
