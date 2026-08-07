import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from './App'

describe('application shell', () => {
  it('renders sectioned navigation and the active route', () => {
    render(<App initialPath="/overview" />)

    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Documentation' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Compliance' })).toBeInTheDocument()
  })

  it('provides profile routes through the account menu', async () => {
    const user = userEvent.setup()
    render(<App initialPath="/overview" />)

    await user.click(screen.getByRole('button', { name: /Workspace owner/i }))
    expect(screen.getByRole('menuitem', { name: 'Settings' })).toHaveAttribute('href', '/settings')
    expect(screen.getByRole('menuitem', { name: 'Integrations' })).toHaveAttribute('href', '/integrations')
    await user.click(screen.getByRole('menuitem', { name: 'Settings' }))
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
  })

  it('collapses the desktop navigation without removing accessible links', async () => {
    const user = userEvent.setup()
    render(<App initialPath="/organizations" />)

    expect(screen.getByRole('heading', { name: 'Organizations' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Collapse navigation' }))
    expect(screen.getByRole('button', { name: 'Expand navigation' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Assets' })).toBeInTheDocument()
  })
})
