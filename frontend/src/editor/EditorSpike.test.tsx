import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

const create = vi.fn().mockResolvedValue(undefined)
const destroy = vi.fn().mockResolvedValue(undefined)
const markdownUpdated = vi.fn()
const editorChain = {
  config: vi.fn(),
  use: vi.fn(),
  action: vi.fn(),
}
const getMarkdown = vi.fn(() => '# Current editor value')
editorChain.config.mockReturnValue(editorChain)
editorChain.use.mockReturnValue(editorChain)

vi.mock('@milkdown/crepe', () => ({
  CrepeFeature: {
    ImageBlock: 'image-block',
    Latex: 'latex',
    Toolbar: 'toolbar',
    TopBar: 'top-bar',
  },
  Crepe: class {
    editor = editorChain

    on(callback: (listener: { markdownUpdated: typeof markdownUpdated }) => void) {
      callback({ markdownUpdated })
    }

    create = create
    destroy = destroy
    getMarkdown = getMarkdown
  },
}))

import { EditorSpike } from './EditorSpike'

describe('editor feasibility spike', () => {
  beforeEach(() => {
    create.mockClear()
    destroy.mockClear()
    markdownUpdated.mockClear()
    editorChain.config.mockClear()
    editorChain.use.mockClear()
    getMarkdown.mockClear()
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

    await waitFor(() => expect(screen.getByRole('button', { name: 'Task list' })).toBeEnabled())
    await user.click(screen.getByRole('tab', { name: 'Markdown' }))
    const source = screen.getByRole('textbox', { name: 'Markdown source' })
    expect((source as HTMLTextAreaElement).value).toBe('# Current editor value')

    fireEvent.change(source, { target: { value: '# Updated procedure' } })
    await user.click(screen.getByRole('tab', { name: 'Editor' }))
    expect(screen.queryByRole('textbox', { name: 'Markdown source' })).not.toBeInTheDocument()
    expect(create).toHaveBeenCalledTimes(2)
  })

  it('exposes visual, source, secure preview, and formatting-help modes', async () => {
    const user = userEvent.setup()
    render(<EditorSpike />)

    expect(screen.getByRole('toolbar', { name: 'Block formatting' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Task list' })).toBeDisabled()
    expect(await screen.findByRole('button', { name: 'Task list' })).toBeEnabled()

    await user.click(screen.getByRole('tab', { name: 'Formatting help' }))
    expect(screen.getByRole('heading', { name: 'TekDocs Markdown' })).toBeInTheDocument()
    expect(screen.getByText('==verify this==')).toBeInTheDocument()
    expect(screen.getByText(/Raw HTML, MDX, scripts/)).toBeInTheDocument()
  })
})
