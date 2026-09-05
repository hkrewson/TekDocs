export type DiagramKind = 'network' | 'flow'
export type DiagramDirection = 'LR' | 'TD'
export type DiagramNodeShape = 'system' | 'decision' | 'terminal' | 'database' | 'document' | 'person' | 'cloud' | 'network-device' | 'input-output' | 'boundary'

export type DiagramNode = {
  id: string
  label: string
  details: string
  shape: DiagramNodeShape
}

export type DiagramConnectionStyle = 'wired' | 'wireless'

export type DiagramConnection = {
  from: string
  to: string
  label: string
  style: DiagramConnectionStyle
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
  return value.trim().replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('\n', ' ')
}

function decodedText(value: string): string {
  return value.replaceAll('&quot;', '"').replaceAll('&gt;', '>').replaceAll('&lt;', '<').replaceAll('&amp;', '&')
}

function wrappedDetails(value: string, width = 32): string {
  const words = value.trim().replaceAll(/\s+/g, ' ').split(' ').filter(Boolean)
  const lines: string[] = []
  for (const word of words) {
    const current = lines.at(-1)
    if (!current || current.length + word.length + 1 > width) lines.push(word)
    else lines[lines.length - 1] = `${current} ${word}`
  }
  return lines.map(safeText).join('<br/>')
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
        { id: 'N1', label: 'Start', details: '', shape: 'terminal' },
        { id: 'N2', label: 'Complete the task', details: '', shape: 'system' },
        { id: 'N3', label: 'Successful?', details: '', shape: 'decision' },
        { id: 'N4', label: 'Finish', details: '', shape: 'terminal' },
      ],
      connections: [
        { from: 'N1', to: 'N2', label: '', style: 'wired' },
        { from: 'N2', to: 'N3', label: '', style: 'wired' },
        { from: 'N3', to: 'N4', label: 'Yes', style: 'wired' },
      ],
    }
  }
  return {
    kind,
    direction: 'LR',
    title: 'Network diagram',
    description: 'The systems and connections in this network.',
    nodes: [
      { id: 'N1', label: 'Internet', details: '', shape: 'system' },
      { id: 'N2', label: 'Firewall', details: '', shape: 'system' },
      { id: 'N3', label: 'Core switch', details: '', shape: 'system' },
    ],
    connections: [
      { from: 'N1', to: 'N2', label: '', style: 'wired' },
      { from: 'N2', to: 'N3', label: '', style: 'wired' },
    ],
  }
}

export function diagramSource(draft: DiagramDraft): string {
  const node = (item: DiagramNode) => {
    const name = safeText(item.label) || item.id
    const details = wrappedDetails(item.details)
    const label = `${name}${details ? `<br/>${details}` : ''}`
    const mermaidShape: Record<DiagramNodeShape, string> = {
      system: 'rect',
      decision: 'diam',
      terminal: 'stadium',
      database: 'cyl',
      document: 'doc',
      person: 'circle',
      cloud: 'cloud',
      'network-device': 'hex',
      'input-output': 'lean-r',
      boundary: 'fr-rect',
    }
    return `${item.id}@{ shape: ${mermaidShape[item.shape]}, label: "${label}" }`
  }
  const lines = [
    `flowchart ${draft.direction}`,
    `accTitle: ${safeText(draft.title) || 'Technical diagram'}`,
    `accDescr: ${safeText(draft.description) || 'Diagram showing documented relationships.'}`,
    ...draft.nodes.map((item) => `  ${node(item)}`),
    ...draft.connections
      .filter((item) => draft.nodes.some((nodeItem) => nodeItem.id === item.from)
        && draft.nodes.some((nodeItem) => nodeItem.id === item.to))
      .map((item) => item.style === 'wireless'
        ? `  ${item.from} ${item.label.trim() ? `-. ${safeEdgeText(item.label)} .->` : '-.->'} ${item.to}`
        : `  ${item.from} -->${item.label.trim() ? `|${safeEdgeText(item.label)}|` : ''} ${item.to}`),
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
      connections.push({ from: connection[1], to: connection[3], label: connection[2] ?? '', style: 'wired' })
      continue
    }
    const wireless = /^([A-Za-z][\w-]*)\s+-\.\s*(.*?)\s*\.->\s+([A-Za-z][\w-]*)$/.exec(line)
    if (wireless) {
      connections.push({ from: wireless[1], to: wireless[3], label: wireless[2], style: 'wireless' })
      continue
    }
    const expanded = /^([A-Za-z][\w-]*)@\{\s*shape:\s*([\w-]+),\s*label:\s*"(.*)"\s*\}$/.exec(line)
    const expandedShape: Record<string, DiagramNodeShape> = {
      rect: 'system', diam: 'decision', stadium: 'terminal', cyl: 'database', doc: 'document', circle: 'person', cloud: 'cloud', hex: 'network-device', 'lean-r': 'input-output', 'fr-rect': 'boundary',
    }
    if (expanded) {
      const shape = expandedShape[expanded[2]]
      if (!shape) return null
      const [label, ...details] = expanded[3].split(/<br\s*\/>/i)
      nodes.push({ id: expanded[1], label: decodedText(label), details: decodedText(details.join(' ')), shape })
      continue
    }
    const terminal = /^([A-Za-z][\w-]*)\(\["(.*)"\]\)$/.exec(line)
    const decision = /^([A-Za-z][\w-]*)\{"(.*)"\}$/.exec(line)
    const system = /^([A-Za-z][\w-]*)\["(.*)"\]$/.exec(line)
    const match = terminal ?? decision ?? system
    if (!match) return null
    nodes.push({
      id: match[1],
      label: decodedText(match[2]),
      details: '',
      shape: terminal ? 'terminal' : decision ? 'decision' : 'system',
    })
  }
  if (!nodes.length) return null
  return {
    kind: nodes.some((item) => item.shape === 'decision' || item.shape === 'terminal' || item.shape === 'input-output') ? 'flow' : 'network',
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
