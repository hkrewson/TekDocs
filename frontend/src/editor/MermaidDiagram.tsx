import DOMPurify from 'dompurify'
import mermaid from 'mermaid'
import { useEffect, useMemo, useState } from 'react'

type DiagramState =
  | { phase: 'loading' }
  | { phase: 'ready'; svg: string }
  | { phase: 'error' }

let initialized = false
let renderQueue = Promise.resolve()

function initializeMermaid() {
  if (initialized) return
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    htmlLabels: false,
    deterministicIds: true,
    deterministicIDSeed: 'tekdocs',
    maxTextSize: 50_000,
    suppressErrorRendering: true,
    theme: 'neutral',
  })
  initialized = true
}

function stableId(source: string, index: number) {
  let hash = 2166136261
  for (let cursor = 0; cursor < source.length; cursor += 1) {
    hash ^= source.charCodeAt(cursor)
    hash = Math.imul(hash, 16777619)
  }
  return `tekdocs-mermaid-${(hash >>> 0).toString(16)}-${index}`
}

function accessibleText(source: string) {
  const title = /^\s*accTitle:\s*(.+)$/im.exec(source)?.[1]?.trim() || 'Technical diagram'
  const description = /^\s*accDescr:\s*(.+)$/im.exec(source)?.[1]?.trim()
  return { title, description }
}

function sanitizeSvg(svg: string) {
  return DOMPurify.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
    FORBID_TAGS: ['foreignObject', 'script'],
  })
}

export function MermaidDiagram({ source, index }: { source: string; index: number }) {
  const [state, setState] = useState<DiagramState>({ phase: 'loading' })
  const accessible = useMemo(() => accessibleText(source), [source])

  useEffect(() => {
    let active = true
    initializeMermaid()
    const render = async () => {
      try {
        const result = await mermaid.render(stableId(source, index), source)
        if (active) setState({ phase: 'ready', svg: sanitizeSvg(result.svg) })
      } catch {
        if (active) setState({ phase: 'error' })
      }
    }
    renderQueue = renderQueue.then(render, render)
    return () => {
      active = false
    }
  }, [index, source])

  return <figure className="mermaid-diagram">
    <figcaption>{accessible.title}</figcaption>
    {accessible.description && <p>{accessible.description}</p>}
    {state.phase === 'loading' && <p role="status">Rendering diagram…</p>}
    {state.phase === 'ready' && <div className="mermaid-graphic" role="img" aria-label={accessible.title}><div aria-hidden="true" dangerouslySetInnerHTML={{ __html: state.svg }} /></div>}
    {state.phase === 'error' && <p role="status">The diagram could not be rendered. Its source remains available below.</p>}
    <details><summary>Accessible diagram source</summary><pre><code>{source}</code></pre></details>
  </figure>
}
