import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from './App'
import type { AuthenticatedContext } from './auth/api'

const authContext: AuthenticatedContext = {
  user: { id: '00000000-0000-4000-8000-000000000001', email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: '00000000-0000-4000-8000-000000000002', name: 'Example MSP' },
}

const app = (initialPath: string) => <App initialPath={initialPath} initialAuthContext={authContext} />

describe('application shell', () => {
  it('renders sectioned navigation and the active route', () => {
    render(app('/overview'))

    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Documentation' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Compliance' })).toBeInTheDocument()
  })

  it('provides profile routes through the account menu', async () => {
    const user = userEvent.setup()
    render(app('/overview'))

    await user.click(screen.getByRole('button', { name: /Account menu for Primary Owner/i }))
    expect(screen.getByRole('menuitem', { name: 'Settings' })).toHaveAttribute('href', '/settings')
    expect(screen.getByRole('menuitem', { name: 'Integrations' })).toHaveAttribute('href', '/integrations')
    await user.click(screen.getByRole('menuitem', { name: 'Settings' }))
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
  })

  it('collapses the desktop navigation without removing accessible links', async () => {
    const user = userEvent.setup()
    render(app('/organizations'))

    expect(screen.getByRole('heading', { name: 'Organizations' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Collapse navigation' }))
    expect(screen.getByRole('button', { name: 'Expand navigation' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Assets' })).toBeInTheDocument()
  })
})
