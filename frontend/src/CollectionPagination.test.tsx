import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { CollectionPagination } from './CollectionPagination'

describe('CollectionPagination', () => {
  it('announces the bounded range and provides keyboard-operable navigation', async () => {
    const onPageChange = vi.fn()
    const user = userEvent.setup()
    render(<CollectionPagination label="Assets" page={2} pageSize={50} count={125} hasMore onPageChange={onPageChange} />)

    const navigation = screen.getByRole('navigation', { name: 'Assets pages' })
    expect(navigation).toHaveTextContent('51–100 of 125')
    await user.click(screen.getByRole('button', { name: 'Previous' }))
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(onPageChange.mock.calls).toEqual([[1], [3]])
  })
})
