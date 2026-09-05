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
  const sanitized = DOMPurify.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
    FORBID_TAGS: ['foreignObject', 'script'],
  })
  const scanned = sanitized.toLowerCase()
    .replace('xmlns="http://www.w3.org/2000/svg"', '')
    .replace('xmlns:xlink="http://www.w3.org/1999/xlink"', '')
  if (['javascript:', 'data:', 'http:', 'https:', '@import'].some((value) => scanned.includes(value))) {
    throw new Error('Unsafe diagram output')
  }
  for (const match of sanitized.matchAll(/url\(([^)]*)\)/gi)) {
    const reference = match[1].trim().replace(/^['"]|['"]$/g, '')
    if (!reference.startsWith('#')) throw new Error('Unsafe diagram output')
  }
  const styles = [
    ...Array.from(sanitized.matchAll(/<style(?:\s[^>]*)?>(.*?)<\/style>/gis), (match) => match[1]),
    ...Array.from(sanitized.matchAll(/\sstyle\s*=\s*(["'])(.*?)\1/gis), (match) => match[2]),
  ]
  if (styles.some((style) => style.includes('\\'))) throw new Error('Unsafe diagram output')
  return sanitized
}

export function MermaidDiagram({ source, index, showSource = false }: { source: string; index: number; showSource?: boolean }) {
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
    {state.phase === 'error' && <p role="status">{showSource ? 'The diagram could not be rendered. Its source remains available below.' : 'The diagram could not be rendered. Open Mermaid source to inspect it.'}</p>}
    {showSource && <details><summary>Accessible diagram source</summary><pre><code>{source}</code></pre></details>}
  </figure>
}
