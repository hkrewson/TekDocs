import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { createMemoryRouter, RouterProvider, useLocation } from 'react-router'
import { NavigationGuardProvider } from '../navigation/NavigationGuardProvider'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import { RecordHeader, RecordSections } from './RecordNavigation'

function Record() {
  const location = useLocation()
  const current = new URLSearchParams(location.search).get('section') ?? 'overview'
  const [draft, setDraft] = useState('')
  useUnsavedChanges(Boolean(draft), false, () => setDraft(''))
  return <article className="record-page">
    <RecordHeader recordId="record-1" section={current} title="Core switch" description="Network hardware" />
    <RecordSections current={current} sections={[
      { id: 'overview', label: 'Overview', href: '/records/record-1?section=overview' },
      { id: 'history', label: 'History', href: '/records/record-1?section=history' },
    ]} />
    <section aria-label={current}><input aria-label="Draft" value={draft} onChange={(event) => setDraft(event.target.value)} /></section>
  </article>
}
function setup(section = 'overview') {
  const state = { assetListPosition: { scrollY: 320, focusId: 'record-1' } }
  const router = createMemoryRouter([{ path: '*', element: <NavigationGuardProvider><Record /></NavigationGuardProvider> }], {
    initialEntries: [{ pathname: '/records/record-1', search: `?section=${section}`, state }],
  })
  render(<RouterProvider router={router} />)
  return { router, state }
}

it('keeps direct section URLs, list-return state, Back/Forward and heading focus', async () => {
  const user = userEvent.setup()
  const { router, state } = setup('history')
  expect(screen.getByRole('link', { name: 'History' })).toHaveAttribute('aria-current', 'page')
  expect(screen.getByRole('link', { name: 'Overview' })).toHaveAttribute('href', '/records/record-1?section=overview')
  await user.click(screen.getByRole('link', { name: 'Overview' }))
  await waitFor(() => expect(router.state.location.search).toBe('?section=overview'))
  expect(router.state.location.state).toEqual(state)
  expect(screen.getByRole('heading', { name: 'Core switch' })).toHaveFocus()
  await act(() => router.navigate(-1))
  expect(screen.getByRole('combobox', { name: 'Sections' })).toHaveValue('history')
  await act(() => router.navigate(1))
  expect(screen.getByRole('link', { name: 'Overview' })).toHaveAttribute('aria-current', 'page')
})

it('guards the mobile section selector and preserves the draft on Keep editing', async () => {
  const user = userEvent.setup()
  const { router, state } = setup()
  await user.type(screen.getByRole('textbox', { name: 'Draft' }), 'Retained value')
  expect(screen.getByRole('textbox', { name: 'Draft' })).toHaveFocus()
  await user.selectOptions(screen.getByRole('combobox', { name: 'Sections' }), 'history')
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(router.state.location.search).toBe('?section=overview')
  expect(screen.getByRole('textbox', { name: 'Draft' })).toHaveValue('Retained value')
  expect(screen.getByRole('combobox', { name: 'Sections' })).toHaveValue('overview')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Sections' }), 'history')
  await user.click(await screen.findByRole('button', { name: 'Discard changes' }))
  await waitFor(() => expect(router.state.location.search).toBe('?section=history'))
  expect(router.state.location.state).toEqual(state)
  expect(screen.getByRole('textbox', { name: 'Draft' })).toHaveValue('')
  expect(screen.getByRole('heading', { name: 'Core switch' })).toHaveFocus()
})
