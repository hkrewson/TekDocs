import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { App } from '../App'
import type { AuthClient, AuthenticatedContext } from './api'

const context: AuthenticatedContext = {
  user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
}

function client(overrides: Partial<AuthClient> = {}): AuthClient {
  return {
    load: vi.fn().mockResolvedValue({ bootstrapRequired: false, context }),
    bootstrapAndLogin: vi.fn().mockResolvedValue(context),
    login: vi.fn().mockResolvedValue(context),
    logout: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

describe('authentication boundary', () => {
  it('does not render the application shell while session state is unresolved', () => {
    render(<App authClient={client({
      load: vi.fn(() => new Promise<{ bootstrapRequired: boolean; context: AuthenticatedContext | null }>(() => undefined)),
    })} />)

    expect(screen.getByRole('status')).toHaveTextContent('Checking installation')
    expect(screen.queryByRole('heading', { name: 'Overview' })).not.toBeInTheDocument()
  })

  it('completes first-owner setup without retaining submitted secrets in the form', async () => {
    const user = userEvent.setup()
    const deploymentToken = crypto.randomUUID()
    const password = `${crypto.randomUUID()}Aa7!`
    const bootstrapAndLogin = vi.fn().mockResolvedValue(context)
    const authClient = client({
      load: vi.fn().mockResolvedValue({ bootstrapRequired: true, context: null }),
      bootstrapAndLogin,
    })
    render(<App authClient={authClient} />)

    await screen.findByRole('heading', { name: 'Set up TekDocs' })
    await user.type(screen.getByLabelText('Deployment token'), deploymentToken)
    await user.type(screen.getByLabelText('MSP name'), 'Example MSP')
    await user.type(screen.getByLabelText('Your name'), 'Primary Owner')
    await user.type(screen.getByLabelText('Email address'), 'owner@example.com')
    await user.type(screen.getByLabelText('Password', { selector: 'input' }), password)
    await user.type(screen.getByLabelText('Confirm password'), password)
    await user.click(screen.getByRole('button', { name: 'Create workspace' }))

    await screen.findByRole('heading', { name: 'Overview' })
    expect(bootstrapAndLogin).toHaveBeenCalledWith({
      deploymentToken,
      tenantName: 'Example MSP',
      ownerDisplayName: 'Primary Owner',
      ownerEmail: 'owner@example.com',
      password,
    })
    expect(screen.queryByDisplayValue(deploymentToken)).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue(password)).not.toBeInTheDocument()
  })

  it('shows a safe sign-in denial and clears the password field', async () => {
    const user = userEvent.setup()
    const authClient = client({
      load: vi.fn().mockResolvedValue({ bootstrapRequired: false, context: null }),
      login: vi.fn().mockRejectedValue(new Error('The email address or password is incorrect.')),
    })
    render(<App authClient={authClient} />)

    await user.type(await screen.findByLabelText('Email address'), 'owner@example.com')
    const password = screen.getByLabelText('Password')
    await user.type(password, crypto.randomUUID())
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('email address or password is incorrect')
    expect(password).toHaveValue('')
    expect(screen.queryByRole('heading', { name: 'Overview' })).not.toBeInTheDocument()
  })

  it('rejects mismatched setup passwords before sending them', async () => {
    const user = userEvent.setup()
    const bootstrapAndLogin = vi.fn()
    render(<App authClient={client({
      load: vi.fn().mockResolvedValue({ bootstrapRequired: true, context: null }),
      bootstrapAndLogin,
    })} />)

    await user.type(await screen.findByLabelText('Deployment token'), crypto.randomUUID())
    await user.type(screen.getByLabelText('MSP name'), 'Example MSP')
    await user.type(screen.getByLabelText('Your name'), 'Primary Owner')
    await user.type(screen.getByLabelText('Email address'), 'owner@example.com')
    await user.type(screen.getByLabelText('Password', { selector: 'input' }), `${crypto.randomUUID()}Aa7!`)
    await user.type(screen.getByLabelText('Confirm password'), `${crypto.randomUUID()}Bb8!`)
    await user.click(screen.getByRole('button', { name: 'Create workspace' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('confirmation does not match')
    expect(bootstrapAndLogin).not.toHaveBeenCalled()
  })

  it('keeps the authenticated shell available when sign out fails', async () => {
    const user = userEvent.setup()
    const authClient = client({ logout: vi.fn().mockRejectedValue(new Error('Sign out was not completed.')) })
    render(<App authClient={authClient} initialAuthContext={context} />)

    await user.click(screen.getByRole('button', { name: /Account menu for Primary Owner/i }))
    await user.click(screen.getByRole('menuitem', { name: 'Sign out' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Sign out was not completed')
    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
  })

  it('retries a failed installation-state request', async () => {
    const user = userEvent.setup()
    const load = vi.fn()
      .mockRejectedValueOnce(new Error('Installation status is unavailable.'))
      .mockResolvedValueOnce({ bootstrapRequired: false, context })
    render(<App authClient={client({ load })} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Installation status is unavailable')
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument())
    expect(load).toHaveBeenCalledTimes(2)
  })
})
