import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

const { initialize, renderDiagram } = vi.hoisted(() => ({
  initialize: vi.fn(),
  renderDiagram: vi.fn().mockResolvedValue({
    svg: '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><foreignObject>unsafe</foreignObject><text>Safe diagram</text></svg>',
  }),
}))

vi.mock('mermaid', () => ({ default: { initialize, render: renderDiagram } }))

import { MermaidDiagram } from './MermaidDiagram'

it('uses strict deterministic rendering and retains an accessible source fallback', async () => {
  const source = 'flowchart LR\naccTitle: Client data flow\naccDescr: Firewall traffic path\nA-->B'
  render(<MermaidDiagram source={source} index={0} />)

  expect(await screen.findByRole('img', { name: 'Client data flow' })).toBeVisible()
  expect(screen.getByText('Firewall traffic path')).toBeVisible()
  expect(screen.getByText('Accessible diagram source')).toBeVisible()
  expect(document.querySelector('details code')?.textContent).toBe(source)
  expect(document.querySelector('script')).not.toBeInTheDocument()
  expect(document.querySelector('foreignObject')).not.toBeInTheDocument()
  expect(initialize).toHaveBeenCalledWith(expect.objectContaining({
    securityLevel: 'strict',
    htmlLabels: false,
    deterministicIds: true,
    maxTextSize: 50_000,
  }))
  expect(renderDiagram).toHaveBeenCalledWith(expect.stringMatching(/^tekdocs-mermaid-/), source)
})
