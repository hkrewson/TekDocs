import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import Overview from './Overview'

it('presents focused operational starting points instead of a capability status table', () => {
  render(<MemoryRouter><Overview /></MemoryRouter>)

  expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Start here' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Client organizations/ })).toHaveAttribute('href', '/organizations')
  expect(screen.getByRole('link', { name: /Search/ })).toHaveAttribute('href', '/search')
  expect(screen.getByRole('link', { name: /Reminders/ })).toHaveAttribute('href', '/deadlines')
  expect(screen.getByRole('link', { name: /Activity/ })).toHaveAttribute('href', '/activity')
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
})
