export type DiagramKind = 'network' | 'flow'
export type DiagramDirection = 'LR' | 'TD'
export type DiagramNodeShape = 'system' | 'decision' | 'terminal'

export type DiagramNode = {
  id: string
  label: string
  shape: DiagramNodeShape
}

export type DiagramConnection = {
  from: string
  to: string
  label: string
}

export type DiagramDraft = {
  kind: DiagramKind
  direction: DiagramDirection
  title: string
  description: string
  nodes: DiagramNode[]
  connections: DiagramConnection[]
}

export type MermaidBlock = {
  start: number
  end: number
  source: string
}

const mermaidFence = /```mermaid[^\n]*\n([\s\S]*?)\n```/gi

export function findMermaidBlocks(markdown: string): MermaidBlock[] {
  return Array.from(markdown.matchAll(mermaidFence), (match) => ({
    start: match.index,
    end: match.index + match[0].length,
    source: match[1],
  }))
}

function safeText(value: string): string {
  return value.trim().replaceAll('"', '&quot;').replaceAll('\n', ' ')
}

function safeEdgeText(value: string): string {
  return safeText(value).replaceAll('|', '/')
}

export function defaultDiagramDraft(kind: DiagramKind = 'network'): DiagramDraft {
  if (kind === 'flow') {
    return {
      kind,
      direction: 'TD',
      title: 'Process flow',
      description: 'The steps and decisions in this process.',
      nodes: [
        { id: 'N1', label: 'Start', shape: 'terminal' },
        { id: 'N2', label: 'Complete the task', shape: 'system' },
        { id: 'N3', label: 'Successful?', shape: 'decision' },
        { id: 'N4', label: 'Finish', shape: 'terminal' },
      ],
      connections: [
        { from: 'N1', to: 'N2', label: '' },
        { from: 'N2', to: 'N3', label: '' },
        { from: 'N3', to: 'N4', label: 'Yes' },
      ],
    }
  }
  return {
    kind,
    direction: 'LR',
    title: 'Network diagram',
    description: 'The systems and connections in this network.',
    nodes: [
      { id: 'N1', label: 'Internet', shape: 'system' },
      { id: 'N2', label: 'Firewall', shape: 'system' },
      { id: 'N3', label: 'Core switch', shape: 'system' },
    ],
    connections: [
      { from: 'N1', to: 'N2', label: '' },
      { from: 'N2', to: 'N3', label: '' },
    ],
  }
}

export function diagramSource(draft: DiagramDraft): string {
  const node = (item: DiagramNode) => {
    const label = safeText(item.label) || item.id
    if (item.shape === 'decision') return `${item.id}{"${label}"}`
    if (item.shape === 'terminal') return `${item.id}(["${label}"])`
    return `${item.id}["${label}"]`
  }
  const lines = [
    `flowchart ${draft.direction}`,
    `accTitle: ${safeText(draft.title) || 'Technical diagram'}`,
    `accDescr: ${safeText(draft.description) || 'Diagram showing documented relationships.'}`,
    ...draft.nodes.map((item) => `  ${node(item)}`),
    ...draft.connections
      .filter((item) => draft.nodes.some((nodeItem) => nodeItem.id === item.from)
        && draft.nodes.some((nodeItem) => nodeItem.id === item.to))
      .map((item) => `  ${item.from} -->${item.label.trim() ? `|${safeEdgeText(item.label)}|` : ''} ${item.to}`),
  ]
  return lines.join('\n')
}

export function parseDiagramSource(source: string): DiagramDraft | null {
  const lines = source.split('\n').map((line) => line.trim()).filter(Boolean)
  const heading = /^flowchart\s+(LR|TD)$/i.exec(lines[0] ?? '')
  if (!heading) return null
  const title = lines.find((line) => line.startsWith('accTitle:'))?.slice('accTitle:'.length).trim() ?? ''
  const description = lines.find((line) => line.startsWith('accDescr:'))?.slice('accDescr:'.length).trim() ?? ''
  const nodes: DiagramNode[] = []
  const connections: DiagramConnection[] = []

  for (const line of lines.slice(1)) {
    if (line.startsWith('accTitle:') || line.startsWith('accDescr:')) continue
    const connection = /^([A-Za-z][\w-]*)\s+-->\s*(?:\|([^|]*)\|\s*)?([A-Za-z][\w-]*)$/.exec(line)
    if (connection) {
      connections.push({ from: connection[1], to: connection[3], label: connection[2] ?? '' })
      continue
    }
    const terminal = /^([A-Za-z][\w-]*)\(\["(.*)"\]\)$/.exec(line)
    const decision = /^([A-Za-z][\w-]*)\{"(.*)"\}$/.exec(line)
    const system = /^([A-Za-z][\w-]*)\["(.*)"\]$/.exec(line)
    const match = terminal ?? decision ?? system
    if (!match) return null
    nodes.push({
      id: match[1],
      label: match[2].replaceAll('&quot;', '"'),
      shape: terminal ? 'terminal' : decision ? 'decision' : 'system',
    })
  }
  if (!nodes.length) return null
  return {
    kind: nodes.some((item) => item.shape !== 'system') ? 'flow' : 'network',
    direction: heading[1].toUpperCase() as DiagramDirection,
    title,
    description,
    nodes,
    connections,
  }
}

export function writeMermaidBlock(markdown: string, source: string, block?: MermaidBlock): string {
  const fence = `\`\`\`mermaid\n${source.trim()}\n\`\`\``
  if (block) return `${markdown.slice(0, block.start)}${fence}${markdown.slice(block.end)}`
  return `${markdown.trimEnd()}${markdown.trim() ? '\n\n' : ''}${fence}\n`
}
