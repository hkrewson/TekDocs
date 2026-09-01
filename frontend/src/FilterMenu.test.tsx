import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { expect, it, vi } from 'vitest'

import { FilterMenu } from './FilterMenu'

function Example({ onClear = vi.fn() }: { onClear?: () => void }) {
  const [type, setType] = useState('')
  return <FilterMenu
    groups={[{ kind: 'choices', label: 'Type', value: type, choices: [{ value: '', label: 'All types' }, { value: 'asset', label: 'Assets' }], onChange: setType }]}
    activeCount={type ? 1 : 0}
    onClear={() => { setType(''); onClear() }}
    menuLabel="Example filters"
  />
}

it('provides the standard filter menu interaction and restores focus', async () => {
  const user = userEvent.setup()
  const onClear = vi.fn()
  render(<Example onClear={onClear} />)

  const trigger = screen.getByRole('button', { name: 'Filters' })
  await user.click(trigger)
  expect(screen.getByRole('dialog', { name: 'Example filters' })).toBeVisible()
  await user.click(screen.getByText('Type', { exact: true }))
  await user.click(screen.getByRole('radio', { name: 'Assets' }))
  expect(trigger).toHaveAccessibleName('Filters (1)')
  await user.click(screen.getByRole('button', { name: 'Clear all filters' }))
  expect(onClear).toHaveBeenCalledOnce()
  expect(trigger).toHaveAccessibleName('Filters')
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog', { name: 'Example filters' })).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
})
