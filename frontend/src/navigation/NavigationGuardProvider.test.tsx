import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { createMemoryRouter, Link, RouterProvider, useLocation, useNavigate } from 'react-router'
import { NavigationGuardProvider } from './NavigationGuardProvider'
import { useUnsavedChanges } from './navigationGuard'

function Form() {
  const [value, setValue] = useState('')
  const [open, setOpen] = useState(true)
  const [busy, setBusy] = useState(false)
  const attempt = useUnsavedChanges(open && Boolean(value), busy, () => setValue(''))
  const location = useLocation()
  const navigate = useNavigate()
  return <>
    <p>{location.pathname}{location.search}</p>
    {open && <input aria-label="Draft" value={value} onChange={(event) => setValue(event.target.value)} />}
    <button onClick={() => attempt(() => setOpen(false))}>Close form</button>
    <button onClick={() => { void navigate(-1) }}>Back</button>
    <button onClick={() => { void navigate(1) }}>Forward</button>
    <button onClick={() => setBusy(true)}>Start request</button>
    <Link to="/other">Other page</Link><Link to="?section=history">History section</Link>
  </>
}
function setup() {
  const router = createMemoryRouter([{ path: '*', element: <NavigationGuardProvider><Form /></NavigationGuardProvider> }], {
    initialEntries: ['/home', '/assets'],
  })
  render(<RouterProvider router={router} />)
  return router
}

it('blocks page and section links, preserves values on Keep editing, and clears them on Discard', async () => {
  const user = userEvent.setup()
  const router = setup()
  await user.type(screen.getByLabelText('Draft'), 'Serial in progress')
  await user.click(screen.getByRole('link', { name: 'Other page' }))
  expect(router.state.location.pathname).toBe('/assets')
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(screen.getByLabelText('Draft')).toHaveValue('Serial in progress')
  await user.click(screen.getByRole('link', { name: 'History section' }))
  await user.click(await screen.findByRole('button', { name: 'Discard changes' }))
  await waitFor(() => expect(router.state.location.search).toBe('?section=history'))
  expect(screen.getByLabelText('Draft')).toHaveValue('')
})

it('guards Back and Forward without adding substitute history entries', async () => {
  const user = userEvent.setup()
  const router = setup()
  await user.type(screen.getByLabelText('Draft'), 'First')
  await user.click(screen.getByRole('button', { name: 'Back' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(router.state.location.pathname).toBe('/assets')
  await user.click(screen.getByRole('button', { name: 'Back' }))
  await user.click(await screen.findByRole('button', { name: 'Discard changes' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/home'))
  await user.type(screen.getByLabelText('Draft'), 'Second')
  await user.click(screen.getByRole('button', { name: 'Forward' }))
  await user.click(await screen.findByRole('button', { name: 'Discard changes' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/assets'))
})

it('guards local closing and registers unload protection only while needed', async () => {
  const user = userEvent.setup()
  setup()
  expect(window.dispatchEvent(new Event('beforeunload', { cancelable: true }))).toBe(true)
  await user.type(screen.getByLabelText('Draft'), 'Unsaved')
  expect(window.dispatchEvent(new Event('beforeunload', { cancelable: true }))).toBe(false)
  await user.click(screen.getByRole('button', { name: 'Close form' }))
  await user.click(await screen.findByRole('button', { name: 'Discard changes' }))
  expect(screen.queryByLabelText('Draft')).not.toBeInTheDocument()
  expect(window.dispatchEvent(new Event('beforeunload', { cancelable: true }))).toBe(true)
})

it('does not discard a pending mutation and treats Escape as Keep editing', async () => {
  const user = userEvent.setup()
  const router = setup()
  await user.type(screen.getByLabelText('Draft'), 'Unsaved')
  await user.click(screen.getByRole('button', { name: 'Start request' }))
  await user.click(screen.getByRole('link', { name: 'Other page' }))
  expect(await screen.findByRole('button', { name: 'Discard changes' })).toBeDisabled()
  expect(screen.getByRole('dialog')).toHaveTextContent('request is still in progress')
  act(() => { screen.getByRole('dialog').dispatchEvent(new Event('cancel', { bubbles: false, cancelable: true })) })
  expect(router.state.location.pathname).toBe('/assets')
  expect(screen.getByLabelText('Draft')).toHaveValue('Unsaved')
})
