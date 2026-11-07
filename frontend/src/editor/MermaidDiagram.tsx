import DOMPurify from 'dompurify'
import { Download, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react'
import { useEffect, useId, useMemo, useState } from 'react'

import { translate } from '../i18n/localization'
import { renderDiagramPreview } from './api'

type DiagramState =
  | { phase: 'loading' }
  | { phase: 'ready'; svg: string }
  | { phase: 'error' }

let renderQueue = Promise.resolve()

function accessibleText(source: string) {
  let title = ''
  let description = ''
  for (const line of source.split(/\r?\n/)) {
    const titleMatch = /^\s*accTitle:\s*(.+?)\s*$/i.exec(line)
    const descriptionMatch = /^\s*accDescr:\s*(.+?)\s*$/i.exec(line)
    if (titleMatch) title = titleMatch[1]
    if (descriptionMatch) description = descriptionMatch[1]
  }
  return { title, description }
}

function sanitizeSvg(svg: string) {
  const sanitized = DOMPurify.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
    FORBID_TAGS: ['foreignObject', 'script'],
  })
  // Inspect decoded attributes, not just scheme substrings: relative and
  // protocol-relative references can also fetch resources or survive SVG download.
  const parsed = new DOMParser().parseFromString(sanitized, 'image/svg+xml')
  if (parsed.querySelector('parsererror') || parsed.documentElement.localName !== 'svg') {
    throw new Error('Unsafe diagram output')
  }
  for (const element of Array.from(parsed.querySelectorAll('*'))) {
    for (const attribute of Array.from(element.attributes)) {
      if (['href', 'src'].includes(attribute.localName) && !attribute.value.trim().startsWith('#')) {
        throw new Error('Unsafe diagram output')
      }
    }
  }
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

function downloadName(title: string) {
  const safe = title.normalize('NFKD').replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '').toLowerCase()
  return `${safe || 'diagram'}.svg`
}

function svgDataUrl(svg: string) {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}

export function MermaidDiagram({
  source,
  index,
  showSource = false,
  showErrorSource = true,
}: {
  source: string
  index: number
  showSource?: boolean
  showErrorSource?: boolean
}) {
  const [state, setState] = useState<DiagramState>({ phase: 'loading' })
  const [zoom, setZoom] = useState(1)
  const accessible = useMemo(() => accessibleText(source), [source])
  const accessibleTitle = accessible.title || 'Technical diagram'
  const descriptionId = useId()

  useEffect(() => {
    let active = true
    const render = async () => {
      try {
        const result = await renderDiagramPreview(source)
        if (active) {
          setState({ phase: 'ready', svg: sanitizeSvg(result.svg) })
          setZoom(1)
        }
      } catch {
        if (active) setState({ phase: 'error' })
      }
    }
    renderQueue = renderQueue.then(render, render)
    return () => {
      active = false
    }
  }, [index, source])

  const downloadSvg = () => {
    if (state.phase !== 'ready') return
    const href = URL.createObjectURL(new Blob([state.svg], { type: 'image/svg+xml;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = href
    link.download = downloadName(accessibleTitle)
    link.click()
    URL.revokeObjectURL(href)
  }

  const sourceVisible = showSource || (showErrorSource && state.phase === 'error')

  return <figure className="mermaid-diagram">
    <figcaption>{accessibleTitle}</figcaption>
    {accessible.description && <p id={descriptionId}>{accessible.description}</p>}
    {state.phase === 'loading' && <p role="status">Rendering diagram…</p>}
    {state.phase === 'ready' && <>
      <div className="diagram-view-toolbar" role="group" aria-label="Diagram view controls">
        <button className="icon-button" type="button" aria-label="Zoom out" title="Zoom out" disabled={zoom <= .5} onClick={() => setZoom((value) => Math.max(.5, value - .25))}><ZoomOut size={16} aria-hidden="true" /></button>
        <button className="diagram-zoom-reset" type="button" aria-label={`Reset zoom, currently ${Math.round(zoom * 100)}%`} title="Reset zoom" disabled={zoom === 1} onClick={() => setZoom(1)}><RotateCcw size={14} aria-hidden="true" /><span aria-hidden="true">{Math.round(zoom * 100)}%</span></button>
        <button className="icon-button" type="button" aria-label="Zoom in" title="Zoom in" disabled={zoom >= 2} onClick={() => setZoom((value) => Math.min(2, value + .25))}><ZoomIn size={16} aria-hidden="true" /></button>
        <button className="secondary-button diagram-download" type="button" onClick={downloadSvg}><Download size={15} aria-hidden="true" />{translate('diagrams.downloadSvg')}</button>
      </div>
      <div className="mermaid-graphic" role="region" tabIndex={0} aria-label={`Scrollable diagram: ${accessibleTitle}`}>
        <div className={`mermaid-graphic-size mermaid-graphic-size-${Math.round(zoom * 100)}`} role="img" aria-label={accessibleTitle} aria-describedby={accessible.description ? descriptionId : undefined}><img src={svgDataUrl(state.svg)} alt="" aria-hidden="true" /></div>
      </div>
    </>}
    {state.phase === 'error' && <p role="status">The diagram could not be rendered. Its Mermaid source remains available below.</p>}
    {sourceVisible && <details><summary>Mermaid source</summary><pre><code>{source}</code></pre></details>}
  </figure>
}
