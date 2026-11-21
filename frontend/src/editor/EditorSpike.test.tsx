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
let crepeOptions: { featureConfigs?: Record<string, { buildMenu?: (builder: unknown) => void }> } | undefined
editorChain.config.mockReturnValue(editorChain)
editorChain.use.mockReturnValue(editorChain)

vi.mock('@milkdown/crepe', () => ({
  CrepeFeature: {
    ImageBlock: 'image-block',
    Latex: 'latex',
    BlockEdit: 'block-edit',
    Toolbar: 'toolbar',
    TopBar: 'top-bar',
  },
  Crepe: class {
    editor = editorChain

    constructor(options: typeof crepeOptions) { crepeOptions = options }

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

  it('adds workspace content and file actions to the slash menu', async () => {
    render(<EditorSpike onInsertCommand={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Task list' })).toBeEnabled())
    const addItem = vi.fn()
    const addGroup = vi.fn(() => ({ addItem }))

    crepeOptions?.featureConfigs?.['block-edit']?.buildMenu?.({ addGroup })

    expect(addGroup).toHaveBeenCalledWith('tekdocs', 'Insert')
    expect(addItem.mock.calls.map((call) => {
      const name = call[0] as string
      const config = call[1] as { label: string }
      return [name, config.label]
    })).toEqual([
      ['document', 'Link to document'],
      ['fragment', 'Insert reusable content'],
      ['record', 'Reference a record'],
      ['file', 'Add a file'],
    ])
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

  it('applies content inserted by an external document tool', async () => {
    const user = userEvent.setup()
    const view = render(<EditorSpike initialMarkdown="Original" />)
    await user.click(screen.getByRole('tab', { name: 'Markdown' }))
    expect(screen.getByRole('textbox', { name: 'Markdown source' })).toHaveValue('# Current editor value')

    view.rerender(<EditorSpike initialMarkdown={'Original\n\n<tekdocs://key/site.name>\n'} />)

    expect(screen.getByRole('textbox', { name: 'Markdown source' })).toHaveValue('Original\n\n<tekdocs://key/site.name>\n')
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
    getMarkdown.mockClear()
    await user.keyboard('{ArrowRight}')

    const previewTab = screen.getByRole('tab', { name: 'Preview' })
    expect(previewTab).toHaveAttribute('aria-selected', 'true')
    expect(previewTab).toHaveFocus()
    expect(getMarkdown).not.toHaveBeenCalled()
  })

  it('opens the diagram editor and shows the rendered preview after insertion', async () => {
    const user = userEvent.setup()
    const onMarkdownChange = vi.fn()
    render(<EditorSpike onMarkdownChange={onMarkdownChange} />)

    const diagrams = await screen.findByRole('button', { name: 'Diagrams' })
    await user.click(diagrams)
    expect(await screen.findByRole('dialog', { name: 'Insert diagram' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Insert diagram' }))

    expect(onMarkdownChange).toHaveBeenLastCalledWith(expect.stringContaining('```mermaid'))
    const preview = screen.getByRole('tab', { name: 'Preview' })
    await waitFor(() => expect(preview).toHaveAttribute('aria-selected', 'true'))
    expect(preview).toHaveFocus()
  })
})
