import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

vi.mock('./MermaidDiagram', () => ({
  MermaidDiagram: ({ source }: { source: string }) => <pre data-testid="diagram-preview">{source}</pre>,
}))

import { DiagramEditor } from './DiagramEditor'

describe('diagram editor', () => {
  it('inserts a portable, accessible Mermaid block', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(<DiagramEditor markdown="# Network" onSave={onSave} onCancel={vi.fn()} />)

    await user.clear(screen.getByRole('textbox', { name: 'Item name 2' }))
    await user.type(screen.getByRole('textbox', { name: 'Item name 2' }), 'Edge firewall')
    await user.click(screen.getByRole('button', { name: 'Insert diagram' }))

    const markdown = onSave.mock.calls[0][0] as string
    expect(markdown).toContain('```mermaid\nflowchart LR')
    expect(markdown).toContain('accTitle: Network diagram')
    expect(markdown).toContain('N2@{ shape: rect, label: "Edge firewall" }')
    expect(markdown).not.toContain('tekdocs:')
  })

  it('edits an existing guided diagram without adding another block', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    const markdown = '# Path\n\n```mermaid\nflowchart LR\naccTitle: Network path\naccDescr: Traffic path.\n  N1["User"]\n  N2["Firewall"]\n  N1 --> N2\n```\n'
    render(<DiagramEditor markdown={markdown} onSave={onSave} onCancel={vi.fn()} />)

    await user.clear(screen.getByRole('textbox', { name: 'Item name 2' }))
    await user.type(screen.getByRole('textbox', { name: 'Item name 2' }), 'Gateway')
    await user.click(screen.getByRole('button', { name: 'Save diagram' }))

    const saved = onSave.mock.calls[0][0] as string
    expect(saved.match(/```mermaid/g)).toHaveLength(1)
    expect(saved).toContain('N2@{ shape: rect, label: "Gateway" }')
  })

  it('keeps unsupported Mermaid diagrams in source mode and closes with Escape', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    const markdown = '```mermaid\nsequenceDiagram\naccTitle: Request\naccDescr: A request and reply.\nAlice->>Bob: Hello\n```\n'
    render(<DiagramEditor markdown={markdown} onSave={vi.fn()} onCancel={onCancel} />)

    expect(screen.getByRole('tab', { name: 'Guided' })).toBeDisabled()
    expect(screen.getByText(/outside the guided editor/)).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('offers the expanded shapes and a concise Mermaid guide without repeating source in preview', async () => {
    const user = userEvent.setup()
    render(<DiagramEditor markdown="" onSave={vi.fn()} onCancel={vi.fn()} />)

    const shapes = screen.getByRole('combobox', { name: 'Item shape 1' })
    expect(shapes).toContainElement(within(shapes).getByRole('option', { name: 'Database' }))
    expect(shapes).toContainElement(within(shapes).getByRole('option', { name: 'Cloud or external service' }))
    expect(screen.queryByText('Accessible diagram source')).not.toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Mermaid guide' }))
    expect(screen.getByRole('heading', { name: 'Mermaid basics' })).toBeVisible()
    expect(screen.getByText('A@{ shape: cyl, label: "Database" }')).toBeVisible()
  })

})
