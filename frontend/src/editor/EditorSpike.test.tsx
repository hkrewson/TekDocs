import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

const create = vi.fn().mockResolvedValue(undefined)
const destroy = vi.fn().mockResolvedValue(undefined)
const markdownUpdated = vi.fn()

vi.mock('@milkdown/crepe', () => ({
  Crepe: class {
    on(callback: (listener: { markdownUpdated: typeof markdownUpdated }) => void) {
      callback({ markdownUpdated })
    }

    create = create
    destroy = destroy
  },
}))

import { EditorSpike } from './EditorSpike'

describe('editor feasibility spike', () => {
  beforeEach(() => {
    create.mockClear()
    destroy.mockClear()
    markdownUpdated.mockClear()
  })

  it('creates and destroys the WYSIWYG editor lifecycle', () => {
    const { unmount } = render(<EditorSpike />)

    expect(create).toHaveBeenCalledOnce()
    unmount()
    expect(destroy).toHaveBeenCalledOnce()
  })

  it('switches to canonical Markdown and carries edits back to the editor', async () => {
    const user = userEvent.setup()
    render(<EditorSpike />)

    await user.click(screen.getByRole('tab', { name: 'Markdown' }))
    const source = screen.getByRole('textbox', { name: 'Markdown source' })
    expect((source as HTMLTextAreaElement).value).toContain('# Firewall replacement')

    fireEvent.change(source, { target: { value: '# Updated procedure' } })
    await user.click(screen.getByRole('tab', { name: 'Editor' }))
    expect(screen.queryByRole('textbox', { name: 'Markdown source' })).not.toBeInTheDocument()
    expect(create).toHaveBeenCalledTimes(2)
  })
})
