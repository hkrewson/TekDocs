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

vi.mock('./MermaidDiagram', () => ({
  MermaidDiagram: ({ source }: { source: string }) => <pre>{source}</pre>,
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

  it('moves focus with the selected editor tab after its panel renders', async () => {
    const user = userEvent.setup()
    render(<EditorSpike />)

    const markdownTab = screen.getByRole('tab', { name: 'Markdown' })
    await user.click(markdownTab)
    await user.keyboard('{ArrowRight}')

    const previewTab = screen.getByRole('tab', { name: 'Preview' })
    expect(previewTab).toHaveAttribute('aria-selected', 'true')
    expect(previewTab).toHaveFocus()
  })

  it('opens the diagram editor and shows the rendered preview after insertion', async () => {
    const user = userEvent.setup()
    const onMarkdownChange = vi.fn()
    render(<EditorSpike onMarkdownChange={onMarkdownChange} />)

    const diagrams = await screen.findByRole('button', { name: 'Diagrams' })
    await user.click(diagrams)
    expect(screen.getByRole('dialog', { name: 'Insert diagram' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Insert diagram' }))

    expect(onMarkdownChange).toHaveBeenLastCalledWith(expect.stringContaining('```mermaid'))
    const preview = screen.getByRole('tab', { name: 'Preview' })
    await waitFor(() => expect(preview).toHaveAttribute('aria-selected', 'true'))
    expect(preview).toHaveFocus()
  })
})
