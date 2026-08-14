import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, vi } from 'vitest'
import { App } from '../App'
import { AuthRequestError } from './api'
import type { AuthClient, AuthenticatedContext } from './api'

const context: AuthenticatedContext = {
  user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
  role: 'owner',
  permissions: ['memberships.view', 'memberships.assign_role', 'organizations.manage_access'],
  surface: 'msp',
  organization: null,
  mfa_enrollment_required: false,
}

function client(overrides: Partial<AuthClient> = {}): AuthClient {
  return {
    load: vi.fn().mockResolvedValue({ bootstrapRequired: false, context }),
    bootstrapAndLogin: vi.fn().mockResolvedValue(context),
    login: vi.fn().mockResolvedValue(context),
    completeMfaLogin: vi.fn().mockResolvedValue(context),
    acceptInvitation: vi.fn().mockResolvedValue(context),
    requestPasswordReset: vi.fn().mockResolvedValue(undefined),
    validatePasswordReset: vi.fn().mockResolvedValue(undefined),
    completePasswordReset: vi.fn().mockResolvedValue(undefined),
    listOidcProviders: vi.fn().mockResolvedValue([]),
    updateProfile: vi.fn().mockResolvedValue(context),
    listSessions: vi.fn().mockResolvedValue([]),
    revokeSession: vi.fn().mockResolvedValue([]),
    loadMfa: vi.fn().mockResolvedValue({ totpEnabled: false, recoveryCodeTotal: 0, recoveryCodeUnused: 0 }),
    beginTotp: vi.fn(),
    activateTotp: vi.fn(),
    regenerateRecoveryCodes: vi.fn(),
    disableTotp: vi.fn(),
    reauthenticate: vi.fn(),
    listApiTokens: vi.fn().mockResolvedValue({ tokens: [], permissions: [] }),
    issueApiToken: vi.fn(),
    rotateApiToken: vi.fn(),
    revokeApiToken: vi.fn(),
    searchTokenOrganizations: vi.fn().mockResolvedValue([]),
    logout: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

beforeEach(() => {
  window.history.replaceState({}, '', '/')
})

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

  it('requires owner MFA enrollment and recovery-code acknowledgement before rendering the workspace', async () => {
    const user = userEvent.setup()
    const recoveryCodes = ['recovery-one', 'recovery-two']
    const activateTotp = vi.fn().mockResolvedValue(recoveryCodes)
    const authClient = client({
      loadMfa: vi.fn().mockResolvedValue({ totpEnabled: false, recoveryCodeTotal: 0, recoveryCodeUnused: 0 }),
      beginTotp: vi.fn().mockResolvedValue({ secret: 'manual-secret', totpUrl: 'otpauth://totp/TekDocs:owner?secret=manual-secret' }),
      activateTotp,
    })
    render(<App authClient={authClient} initialAuthContext={{ ...context, mfa_enrollment_required: true }} />)

    expect(await screen.findByRole('heading', { name: 'Secure the owner account' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Overview' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Set up authenticator' }))
    await user.type(await screen.findByLabelText('Authentication code'), '123456')
    await user.click(screen.getByRole('button', { name: 'Enable two-factor authentication' }))

    expect(await screen.findByText('recovery-one')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: /saved the recovery codes/i }))
    await user.click(screen.getByRole('button', { name: 'Continue' }))
    expect(await screen.findByRole('heading', { name: 'Setup complete' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Enter MSP workspace' }))

    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    expect(activateTotp).toHaveBeenCalledWith('123456')
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

  it('offers only the configured public OIDC provider descriptor', async () => {
    const provider = { id: 'company-sso', name: 'Company SSO' }
    document.cookie = `csrftoken=${crypto.randomUUID()}; path=/`
    render(<App authClient={client({
      load: vi.fn().mockResolvedValue({ bootstrapRequired: false, context: null }),
      listOidcProviders: vi.fn().mockResolvedValue([provider]),
    })} />)

    const button = await screen.findByRole('button', { name: 'Continue with Company SSO' })
    const form = button.closest('form')
    expect(form).toHaveAttribute('action', '/_allauth/browser/v1/auth/provider/redirect')
    expect(form?.querySelector('input[name="provider"]')).toHaveAttribute('value', 'company-sso')
    expect(form?.textContent).not.toContain('secret')
  })

  it('completes the pending two-factor challenge without retaining the code', async () => {
    const user = userEvent.setup()
    const completeMfaLogin = vi.fn().mockResolvedValue(context)
    render(<App authClient={client({
      load: vi.fn().mockResolvedValue({ bootstrapRequired: false, context: null }),
      login: vi.fn().mockResolvedValue({ mfaRequired: true }),
      completeMfaLogin,
    })} />)

    await user.type(await screen.findByLabelText('Email address'), 'owner@example.com')
    await user.type(screen.getByLabelText('Password'), `${crypto.randomUUID()}Aa7!`)
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await screen.findByRole('heading', { name: 'Two-factor authentication' })
    const code = `recovery-${crypto.randomUUID()}`
    const codeInput = screen.getByLabelText('Authentication code')
    await user.type(codeInput, code)
    await user.click(screen.getByRole('button', { name: 'Verify code' }))

    await screen.findByRole('heading', { name: 'Overview' })
    expect(completeMfaLogin).toHaveBeenCalledWith(code)
    expect(screen.queryByDisplayValue(code)).not.toBeInTheDocument()
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

  it('activates an invited account without retaining the URL token or password', async () => {
    const user = userEvent.setup()
    const token = `${crypto.randomUUID().replaceAll('-', '')}${crypto.randomUUID().replaceAll('-', '')}`
    const password = `${crypto.randomUUID()}Aa7!`
    const acceptInvitation = vi.fn().mockResolvedValue(context)
    window.history.replaceState({}, '', `/auth/invitations/accept#token=${token}`)
    render(<App authClient={client({ acceptInvitation })} />)

    expect(screen.getByRole('heading', { name: 'Accept invitation' })).toBeInTheDocument()
    expect(window.location.hash).toBe('')
    await user.type(screen.getByLabelText('Your name'), 'Invited Technician')
    await user.type(screen.getByLabelText('Password', { selector: 'input' }), password)
    await user.type(screen.getByLabelText('Confirm password'), password)
    await user.click(screen.getByRole('button', { name: 'Activate account' }))

    await screen.findByRole('heading', { name: 'Overview' })
    expect(acceptInvitation).toHaveBeenCalledWith({ token, displayName: 'Invited Technician', password })
    expect(window.location.pathname).toBe('/overview')
    expect(screen.queryByDisplayValue(token)).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue(password)).not.toBeInTheDocument()
  })

  it('uses one safe unavailable state for a rejected or missing invitation', async () => {
    const user = userEvent.setup()
    const token = `${crypto.randomUUID().replaceAll('-', '')}${crypto.randomUUID().replaceAll('-', '')}`
    window.history.replaceState({}, '', `/auth/invitations/accept#token=${token}`)
    render(<App authClient={client({
      acceptInvitation: vi.fn().mockRejectedValue(new AuthRequestError('Invitation unavailable', 410)),
    })} />)

    await user.type(screen.getByLabelText('Your name'), 'Invited Technician')
    const password = `${crypto.randomUUID()}Aa7!`
    await user.type(screen.getByLabelText('Password', { selector: 'input' }), password)
    await user.type(screen.getByLabelText('Confirm password'), password)
    await user.click(screen.getByRole('button', { name: 'Activate account' }))

    expect(await screen.findByRole('heading', { name: 'Invitation unavailable' })).toBeInTheDocument()
    expect(screen.getByText(/missing, expired, revoked, or has already been used/i)).toBeInTheDocument()
    expect(screen.queryByDisplayValue(password)).not.toBeInTheDocument()
  })

  it('offers an enumeration-safe password reset request from sign in', async () => {
    const user = userEvent.setup()
    const requestPasswordReset = vi.fn().mockResolvedValue(undefined)
    render(<App authClient={client({
      load: vi.fn().mockResolvedValue({ bootstrapRequired: false, context: null }),
      requestPasswordReset,
    })} />)

    await user.click(await screen.findByRole('button', { name: 'Forgot password?' }))
    await user.type(screen.getByLabelText('Email address'), 'someone@example.com')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))

    expect(requestPasswordReset).toHaveBeenCalledWith('someone@example.com')
    expect(await screen.findByRole('heading', { name: 'Check your email' })).toBeInTheDocument()
    expect(screen.getByText(/same message is shown for every address/i)).toBeInTheDocument()
  })

  it('scrubs the reset key and completes a validated password reset', async () => {
    const user = userEvent.setup()
    const key = `${crypto.randomUUID()}-${crypto.randomUUID()}`
    const password = `${crypto.randomUUID()}Aa7!`
    const validatePasswordReset = vi.fn().mockResolvedValue(undefined)
    const completePasswordReset = vi.fn().mockResolvedValue(undefined)
    window.history.replaceState({}, '', `/auth/reset-password#key=${encodeURIComponent(key)}`)
    render(<App authClient={client({ validatePasswordReset, completePasswordReset })} />)

    expect(window.location.hash).toBe('')
    await screen.findByRole('heading', { name: 'Choose a new password' })
    await user.type(screen.getByLabelText('New password', { exact: true }), password)
    await user.type(screen.getByLabelText('Confirm new password'), password)
    await user.click(screen.getByRole('button', { name: 'Change password' }))

    expect(validatePasswordReset).toHaveBeenCalledWith(key)
    expect(completePasswordReset).toHaveBeenCalledWith(key, password)
    expect(await screen.findByRole('heading', { name: 'Password changed' })).toBeInTheDocument()
    expect(screen.queryByDisplayValue(password)).not.toBeInTheDocument()
  })

  it('shows one unavailable state when a reset key cannot be validated', async () => {
    const key = `${crypto.randomUUID()}-${crypto.randomUUID()}`
    window.history.replaceState({}, '', `/auth/reset-password#key=${encodeURIComponent(key)}`)
    render(<App authClient={client({
      validatePasswordReset: vi.fn().mockRejectedValue(new AuthRequestError('Invalid', 400)),
    })} />)

    expect(await screen.findByRole('heading', { name: 'Reset link unavailable' })).toBeInTheDocument()
    expect(screen.getByText(/invalid, expired, or has already been used/i)).toBeInTheDocument()
  })
})
