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

  it('round-trips every shape exposed by the guided editor', () => {
    const draft = defaultDiagramDraft('network')
    draft.nodes = (['system', 'decision', 'terminal', 'database', 'document', 'person', 'cloud', 'network-device', 'input-output', 'boundary'] as const)
      .map((shape, index) => ({ id: `N${index + 1}`, label: shape, details: '', shape }))
    draft.connections = [{ from: 'N1', to: 'N2', label: 'uses', style: 'wired' }]

    expect(parseDiagramSource(diagramSource(draft))?.nodes).toEqual(draft.nodes)
  })

  it('round-trips wrapped details and wireless connections', () => {
    const draft = defaultDiagramDraft('network')
    draft.nodes[1].details = 'Gateway · 192.0.2.1\nPrimary site'
    draft.connections[0] = { ...draft.connections[0], label: 'Wi-Fi 6', style: 'wireless' }

    const source = diagramSource(draft)
    expect(source).toContain('Firewall<br/>Gateway · 192.0.2.1 Primary site')
    expect(source).toContain('N1 -. Wi-Fi 6 .-> N2')
    expect(parseDiagramSource(source)).toEqual({
      ...draft,
      nodes: draft.nodes.map((node) => ({ ...node, details: node.details.replace('\n', ' ') })),
    })
  })

  it('wraps long item details without losing their text', () => {
    const draft = defaultDiagramDraft('network')
    draft.nodes[1].details = 'Primary gateway for the main office and guest wireless networks'

    const source = diagramSource(draft)
    expect(source).toContain('Primary gateway for the main<br/>office and guest wireless<br/>networks')
    expect(parseDiagramSource(source)?.nodes[1].details).toBe(draft.nodes[1].details)
  })
})
