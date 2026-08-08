import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { SecuritySettings } from './SecuritySettings'
import { AuthRequestError } from './api'
import type { AuthClient, AuthenticatedContext, AuthSession } from './api'

const context: AuthenticatedContext = {
  user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
}

const current: AuthSession = {
  id: 1,
  userAgent: 'Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/140.0 Safari/537.36',
  ip: '192.0.2.10',
  createdAt: 1_786_000_000,
  lastSeenAt: 1_786_003_600,
  isCurrent: true,
}

const other: AuthSession = {
  id: 2,
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/141.0',
  ip: '198.51.100.20',
  createdAt: 1_785_000_000,
  lastSeenAt: 1_785_003_600,
  isCurrent: false,
}

function client(overrides: Partial<AuthClient> = {}): AuthClient {
  return {
    listSessions: vi.fn().mockResolvedValue([current, other]),
    revokeSession: vi.fn().mockResolvedValue([current]),
    loadMfa: vi.fn().mockResolvedValue({ totpEnabled: false, recoveryCodeTotal: 0, recoveryCodeUnused: 0 }),
    updateProfile: vi.fn().mockResolvedValue(context),
    ...overrides,
  } as AuthClient
}

const settings = (authClient: AuthClient, onProfileUpdated = vi.fn()) => (
  <SecuritySettings client={authClient} context={context} onProfileUpdated={onProfileUpdated} />
)

describe('security settings', () => {
  it('lists active sessions and revokes another browser', async () => {
    const user = userEvent.setup()
    const revokeSession = vi.fn().mockResolvedValue([current])
    render(settings(client({ revokeSession })))

    expect(await screen.findByText('Chrome on macOS')).toBeInTheDocument()
    expect(screen.getByText('Firefox on Windows')).toBeInTheDocument()
    expect(screen.getByText('Current session')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Revoke' }))

    expect(revokeSession).toHaveBeenCalledWith(2)
    await waitFor(() => expect(screen.queryByText('Firefox on Windows')).not.toBeInTheDocument())
  })

  it('keeps the list visible when server-side revocation is denied', async () => {
    const user = userEvent.setup()
    render(settings(client({ revokeSession: vi.fn().mockRejectedValue(new Error('The session could not be revoked.')) })))

    await screen.findByText('Firefox on Windows')
    await user.click(screen.getByRole('button', { name: 'Revoke' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The session could not be revoked.')
    expect(screen.getByText('Firefox on Windows')).toBeInTheDocument()
  })

  it('offers a retry when sessions cannot be loaded', async () => {
    const user = userEvent.setup()
    const listSessions = vi.fn()
      .mockRejectedValueOnce(new Error('Active sessions could not be loaded.'))
      .mockResolvedValueOnce([current])
    render(settings(client({ listSessions })))

    expect(await screen.findByRole('alert')).toHaveTextContent('Active sessions could not be loaded.')
    await user.click(screen.getByRole('button', { name: 'Refresh' }))

    expect(await screen.findByText('Chrome on macOS')).toBeInTheDocument()
    expect(listSessions).toHaveBeenCalledTimes(2)
  })

  it('enrolls an authenticator and shows recovery codes only until acknowledged', async () => {
    const user = userEvent.setup()
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
    const secret = Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) => alphabet[value % alphabet.length]).join('')
    const setup = { secret, totpUrl: `otpauth://totp/TekDocs:owner?secret=${secret}` }
    const recoveryCodes = ['alpha-bravo', 'charlie-delta']
    const activateTotp = vi.fn().mockResolvedValue(recoveryCodes)
    render(settings(client({
      beginTotp: vi.fn().mockResolvedValue(setup),
      activateTotp,
    })))

    await user.click(await screen.findByRole('button', { name: 'Set up authenticator' }))
    expect(document.querySelector('.mfa-qr-code svg')).toBeInTheDocument()
    expect(document.querySelector('.mfa-qr-code svg')).toHaveAttribute('width', '192')
    expect(screen.getByText('Scan with your authenticator app')).toBeInTheDocument()
    expect(screen.getByText(secret)).toBeInTheDocument()
    expect(screen.getByText(setup.totpUrl)).not.toBeVisible()
    await user.click(screen.getByText('Show setup address'))
    expect(screen.getByText(setup.totpUrl)).toBeInTheDocument()
    await user.type(screen.getByLabelText('Authentication code'), '123456')
    await user.click(screen.getByRole('button', { name: 'Enable two-factor authentication' }))

    expect(activateTotp).toHaveBeenCalledWith('123456')
    expect(await screen.findByText('alpha-bravo')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'I saved these codes' }))
    expect(screen.queryByText('alpha-bravo')).not.toBeInTheDocument()
    expect(screen.getByText('2 of 2 codes remain. Each code works once.')).toBeInTheDocument()
  })

  it('requires a password recheck before replacing recovery codes', async () => {
    const user = userEvent.setup()
    const password = `${crypto.randomUUID()}Aa7!`
    const reauthenticate = vi.fn().mockResolvedValue(undefined)
    const regenerateRecoveryCodes = vi.fn().mockResolvedValue(['new-one', 'new-two'])
    render(settings(client({
      loadMfa: vi.fn().mockResolvedValue({ totpEnabled: true, recoveryCodeTotal: 10, recoveryCodeUnused: 7 }),
      reauthenticate,
      regenerateRecoveryCodes,
    })))

    await user.click(await screen.findByRole('button', { name: 'Replace codes' }))
    const passwordInput = screen.getByLabelText('Current password')
    await user.type(passwordInput, password)
    await user.click(screen.getByRole('button', { name: 'Confirm change' }))

    expect(reauthenticate).toHaveBeenCalledWith(password)
    expect(regenerateRecoveryCodes).toHaveBeenCalledOnce()
    expect(passwordInput).toHaveValue('')
    expect(await screen.findByText('new-one')).toBeInTheDocument()
  })

  it('reauthenticates an expired enrollment without replacing the scanned secret', async () => {
    const user = userEvent.setup()
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
    const secret = Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) => alphabet[value % alphabet.length]).join('')
    const setup = { secret, totpUrl: `otpauth://totp/TekDocs:owner?secret=${secret}` }
    const beginTotp = vi.fn().mockResolvedValue(setup)
    const activateTotp = vi.fn()
      .mockRejectedValueOnce(new AuthRequestError('Password confirmation required.', 401))
      .mockResolvedValueOnce(['new-one', 'new-two'])
    const reauthenticate = vi.fn().mockResolvedValue(undefined)
    render(settings(client({ beginTotp, activateTotp, reauthenticate })))

    await user.click(await screen.findByRole('button', { name: 'Set up authenticator' }))
    await user.type(screen.getByLabelText('Authentication code'), '111111')
    await user.click(screen.getByRole('button', { name: 'Enable two-factor authentication' }))

    expect(await screen.findByText(/password confirmation expired/i)).toBeInTheDocument()
    expect(document.querySelector('.mfa-qr-code svg')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Current password'), 'temporary-password')
    await user.click(screen.getByRole('button', { name: 'Confirm change' }))

    expect(reauthenticate).toHaveBeenCalledWith('temporary-password')
    expect(await screen.findByRole('status')).toHaveTextContent('Enter the current code')
    expect(document.querySelector('.mfa-qr-code svg')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Authentication code'), '222222')
    await user.click(screen.getByRole('button', { name: 'Enable two-factor authentication' }))

    expect(beginTotp).toHaveBeenCalledOnce()
    expect(activateTotp).toHaveBeenNthCalledWith(1, '111111')
    expect(activateTotp).toHaveBeenNthCalledWith(2, '222222')
    expect(await screen.findByText('new-one')).toBeInTheDocument()
  })

  it('updates the display name while keeping the sign-in email read-only', async () => {
    const user = userEvent.setup()
    const updated = { ...context, user: { ...context.user, display_name: 'Operations Lead' } }
    const updateProfile = vi.fn().mockResolvedValue(updated)
    const onProfileUpdated = vi.fn()
    render(settings(client({ updateProfile }), onProfileUpdated))

    const displayName = screen.getByLabelText('Display name')
    await user.clear(displayName)
    await user.type(displayName, 'Operations Lead')
    expect(screen.getByLabelText('Email address')).toHaveAttribute('readonly')
    await user.click(screen.getByRole('button', { name: 'Save profile' }))

    expect(updateProfile).toHaveBeenCalledWith('Operations Lead')
    expect(onProfileUpdated).toHaveBeenCalledWith(updated)
    expect(await screen.findByRole('status')).toHaveTextContent('Profile updated')
  })
})
