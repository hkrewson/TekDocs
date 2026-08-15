import { lazy, Suspense, useEffect, useMemo, useRef } from 'react'
import { createRoot } from 'react-dom/client'

import { sanitizeMarkdownHtml } from './sanitize'

const MermaidDiagram = lazy(async () => ({ default: (await import('./MermaidDiagram')).MermaidDiagram }))

export function SanitizedMarkdown({ html }: { html: string }) {
  const sanitized = useMemo(() => sanitizeMarkdownHtml(html), [html])
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const candidates = Array.from(container.current?.querySelectorAll('pre > code.language-mermaid') ?? []).slice(0, 20)
    const mounted = candidates.flatMap((code, index) => {
      const source = code.textContent ?? ''
      const sourceBlock = code.parentElement
      if (source.length === 0 || source.length > 50_000 || !sourceBlock?.isConnected) return []
      const target = document.createElement('div')
      sourceBlock.hidden = true
      sourceBlock.insertAdjacentElement('afterend', target)
      const root = createRoot(target)
      root.render(
        <Suspense fallback={<p role="status">Loading diagram renderer…</p>}>
          <MermaidDiagram source={source} index={index} />
        </Suspense>,
      )
      return [{ root, sourceBlock, target }]
    })
    return () => {
      mounted.forEach(({ root, sourceBlock, target }) => {
        sourceBlock.hidden = false
        target.remove()
        window.setTimeout(() => root.unmount(), 0)
      })
    }
  }, [sanitized])

  return <div ref={container} className="markdown-preview" dangerouslySetInnerHTML={{ __html: sanitized }} />
}
