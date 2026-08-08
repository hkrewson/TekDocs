import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { SecuritySettings } from './SecuritySettings'
import type { AuthClient, AuthSession } from './api'

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
    ...overrides,
  } as AuthClient
}

describe('security settings', () => {
  it('lists active sessions and revokes another browser', async () => {
    const user = userEvent.setup()
    const revokeSession = vi.fn().mockResolvedValue([current])
    render(<SecuritySettings client={client({ revokeSession })} />)

    expect(await screen.findByText('Chrome on macOS')).toBeInTheDocument()
    expect(screen.getByText('Firefox on Windows')).toBeInTheDocument()
    expect(screen.getByText('Current session')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Revoke' }))

    expect(revokeSession).toHaveBeenCalledWith(2)
    await waitFor(() => expect(screen.queryByText('Firefox on Windows')).not.toBeInTheDocument())
  })

  it('keeps the list visible when server-side revocation is denied', async () => {
    const user = userEvent.setup()
    render(<SecuritySettings client={client({ revokeSession: vi.fn().mockRejectedValue(new Error('The session could not be revoked.')) })} />)

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
    render(<SecuritySettings client={client({ listSessions })} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Active sessions could not be loaded.')
    await user.click(screen.getByRole('button', { name: 'Refresh' }))

    expect(await screen.findByText('Chrome on macOS')).toBeInTheDocument()
    expect(listSessions).toHaveBeenCalledTimes(2)
  })
})
