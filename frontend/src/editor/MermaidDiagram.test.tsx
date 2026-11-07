import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

const { renderDiagram } = vi.hoisted(() => ({
  renderDiagram: vi.fn().mockResolvedValue({
    svg: '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><foreignObject>unsafe</foreignObject><text>Safe diagram</text></svg>',
    title: 'Technical diagram',
    description: '',
    rendererVersion: '@mermaid-js/mermaid-cli@11.16.0',
  }),
}))

vi.mock('./api', () => ({ renderDiagramPreview: renderDiagram }))

import { MermaidDiagram } from './MermaidDiagram'

function renderedSvg(graphic: HTMLElement) {
  const source = graphic.querySelector('img')?.getAttribute('src')
  expect(source).toMatch(/^data:image\/svg\+xml;charset=utf-8,/)
  return decodeURIComponent(source!.slice(source!.indexOf(',') + 1))
}

it('uses isolated rendering and retains an accessible source fallback', async () => {
  const source = 'flowchart LR\naccTitle: Client data flow\naccDescr: Firewall traffic path\nA-->B'
  render(<MermaidDiagram source={source} index={0} showSource />)

  expect(await screen.findByRole('img', { name: 'Client data flow' })).toBeVisible()
  expect(screen.getByText('Firewall traffic path')).toBeVisible()
  expect(screen.getByText('Mermaid source')).toBeVisible()
  expect(document.querySelector('details code')?.textContent).toBe(source)
  const svg = renderedSvg(screen.getByRole('img', { name: 'Client data flow' }))
  expect(svg).not.toContain('<script')
  expect(svg).not.toContain('<foreignObject')
  expect(renderDiagram).toHaveBeenCalledWith(source)
})

it('refuses obfuscated external CSS references in renderer output', async () => {
  renderDiagram.mockResolvedValueOnce({
    svg: '<svg xmlns="http://www.w3.org/2000/svg"><rect style="fill:u\\72l(\\68ttps\\3a//example.invalid/x)"/></svg>',
    title: 'Technical diagram', description: '', rendererVersion: '@mermaid-js/mermaid-cli@11.16.0',
  })

  render(<MermaidDiagram source="flowchart LR\nA-->B" index={1} showSource />)

  expect(await screen.findByText('The diagram could not be rendered. Its Mermaid source remains available below.')).toBeVisible()
  expect(screen.getByText('Mermaid source')).toBeVisible()
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
})

it('can omit the source disclosure in a guided editing context', async () => {
  render(<MermaidDiagram source="flowchart LR\naccTitle: Path\naccDescr: A path\nA-->B" index={2} showSource={false} />)

  expect(await screen.findByRole('img')).toBeVisible()
  expect(screen.queryByText('Mermaid source')).not.toBeInTheDocument()
})

it.each([
  '<image href="//example.invalid/tracking.svg"/>',
  '<image href="/external.svg"/>',
  '<image xlink:href="relative.svg#diagram"/>',
  '<image href="&#47;&#47;example.invalid/tracking.svg"/>',
])('refuses non-fragment SVG references: %s', async (reference) => {
  renderDiagram.mockResolvedValueOnce({
    svg: `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">${reference}</svg>`,
    title: 'Technical diagram', description: '', rendererVersion: '@mermaid-js/mermaid-cli@11.16.0',
  })
  render(<MermaidDiagram source="flowchart LR\nA-->B" index={4} showSource />)

  expect(await screen.findByText('The diagram could not be rendered. Its Mermaid source remains available below.')).toBeVisible()
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Download SVG' })).not.toBeInTheDocument()
})

it('retains local fragment links and paint references', async () => {
  renderDiagram.mockResolvedValueOnce({
    svg: '<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="ink"/></defs><rect fill="url(#ink)"/><a href="#label"><text id="label">Local reference</text></a></svg>',
    title: 'Technical diagram', description: '', rendererVersion: '@mermaid-js/mermaid-cli@11.16.0',
  })
  render(<MermaidDiagram source="flowchart LR\nA-->B" index={5} />)

  const graphic = await screen.findByRole('img')
  const svg = renderedSvg(graphic)
  expect(svg).toContain('href="#label"')
  expect(svg).toContain('fill="url(#ink)"')
  expect(screen.getByRole('button', { name: 'Download SVG' })).toBeEnabled()
})

it('zooms with keyboard-operable controls and downloads sanitized SVG', async () => {
  const user = userEvent.setup()
  const source = `flowchart LR
accTitle: Client path
accDescr: A path
A-->B`
  render(<MermaidDiagram source={source} index={3} />)

  const graphic = await screen.findByRole('img', { name: 'Client path' })
  expect(graphic).toHaveAttribute('aria-describedby')
  expect(screen.getByRole('region', { name: 'Scrollable diagram: Client path' })).toHaveAttribute('tabindex', '0')
  await user.click(screen.getByRole('button', { name: 'Zoom in' }))
  expect(graphic).toHaveClass('mermaid-graphic-size-125')
  await user.click(screen.getByRole('button', { name: 'Reset zoom, currently 125%' }))
  expect(graphic).toHaveClass('mermaid-graphic-size-100')
  const createObjectUrl = vi.fn().mockReturnValue('blob:diagram')
  const revokeObjectUrl = vi.fn()
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectUrl })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectUrl })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  await user.click(screen.getByRole('button', { name: 'Download SVG' }))
  expect(createObjectUrl).toHaveBeenCalledWith(expect.any(Blob))
  expect(click).toHaveBeenCalledOnce()
  expect(revokeObjectUrl).toHaveBeenCalledWith('blob:diagram')
})
