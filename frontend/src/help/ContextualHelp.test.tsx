import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it } from 'vitest'

import { ContextualHelp } from './ContextualHelp'

afterEach(() => { document.body.style.overflow = '' })

it('opens focused route help and restores focus after Escape', async () => {
  const user = userEvent.setup()
  render(<ContextualHelp pathname="/system-status" />)

  const trigger = screen.getByRole('button', { name: 'Help for System status' })
  await user.click(trigger)

  const dialog = screen.getByRole('dialog', { name: 'System status help' })
  expect(dialog).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'System status' })).toHaveFocus()
  expect(document.body.style.overflow).toBe('hidden')
  expect(screen.getByText(/database, and the isolated diagram renderer/)).toBeInTheDocument()

  await user.keyboard('{Escape}')
  expect(dialog).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
  expect(document.body.style.overflow).toBe('')
})

it('closes from the explicit small-screen action', async () => {
  const user = userEvent.setup()
  render(<ContextualHelp pathname="/documentation" />)

  await user.click(screen.getByRole('button', { name: 'Help for Documentation' }))
  await user.click(screen.getByRole('button', { name: 'Close help' }))

  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Help for Documentation' })).toHaveFocus()
})

it('keeps keyboard focus inside the open help dialog', async () => {
  const user = userEvent.setup()
  render(<ContextualHelp pathname="/documentation" />)

  await user.click(screen.getByRole('button', { name: 'Help for Documentation' }))
  const close = screen.getByRole('button', { name: 'Close help' })
  await user.keyboard('{Tab}')
  expect(close).toHaveFocus()
  await user.keyboard('{Tab}')
  const guide = screen.getByRole('link', { name: 'Open the full guide' })
  expect(guide).toHaveFocus()
  await user.keyboard('{Tab}')
  expect(close).toHaveFocus()
  await user.keyboard('{Shift>}{Tab}{/Shift}')
  expect(guide).toHaveFocus()
})


it('offers the published route guide in a separate tab without a referrer', async () => {
  const user = userEvent.setup()
  render(<ContextualHelp pathname="/documentation" />)
  await user.click(screen.getByRole('button', { name: 'Help for Documentation' }))
  const guide = screen.getByRole('link', { name: 'Open the full guide' })
  expect(guide).toHaveAttribute('href', 'https://github.com/hkrewson/TekDocs/wiki/Documentation')
  expect(guide).toHaveAttribute('target', '_blank')
  expect(guide).toHaveAttribute('rel', 'noreferrer')
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})
