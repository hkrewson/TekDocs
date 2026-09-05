import { defaultDiagramDraft, diagramSource, findMermaidBlocks, parseDiagramSource, writeMermaidBlock } from './diagramBlocks'

describe('Markdown diagram blocks', () => {
  it('round-trips the guided network and flow formats without private metadata', () => {
    for (const kind of ['network', 'flow'] as const) {
      const source = diagramSource(defaultDiagramDraft(kind))
      expect(parseDiagramSource(source)).toEqual(defaultDiagramDraft(kind))
      expect(source).not.toContain('tekdocs:')
    }
  })

  it('finds, replaces, and appends Mermaid fences while preserving the document', () => {
    const original = '# Network\n\nBefore\n\n```mermaid\nflowchart LR\nA["Old"]\n```\n\nAfter\n'
    const block = findMermaidBlocks(original)[0]
    const replaced = writeMermaidBlock(original, 'flowchart LR\nB["New"]', block)
    expect(replaced).toContain('# Network\n\nBefore')
    expect(replaced).toContain('B["New"]')
    expect(replaced).toContain('\n\nAfter\n')
    expect(findMermaidBlocks(writeMermaidBlock(replaced, 'flowchart TD\nC["Third"]'))).toHaveLength(2)
  })

  it('leaves unsupported Mermaid syntax available for source editing', () => {
    expect(parseDiagramSource('sequenceDiagram\nAlice->>Bob: Hello')).toBeNull()
  })
})
