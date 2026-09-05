import { createElement, lazy, Suspense, useMemo } from 'react'
import type { ReactNode } from 'react'

import { sanitizeMarkdownHtml } from './sanitize'

const MermaidDiagram = lazy(async () => ({ default: (await import('./MermaidDiagram')).MermaidDiagram }))

function renderedMarkdown(html: string): ReactNode[] {
  const sanitized = sanitizeMarkdownHtml(html)
  const parsed = document.createElement('div')
  parsed.innerHTML = sanitized
  let diagramIndex = 0

  const renderNode = (node: Node, key: string): ReactNode => {
    if (node.nodeType === 3) return node.textContent
    if (node.nodeType !== 1) return null
    const element = node as HTMLElement
    const mermaidCode = element.tagName === 'PRE' && element.children.length === 1
      ? element.firstElementChild
      : null
    if (diagramIndex < 20 && mermaidCode?.tagName === 'CODE' && mermaidCode.classList.contains('language-mermaid')) {
      const source = mermaidCode.textContent ?? ''
      if (source.length > 0 && source.length <= 50_000) {
        const index = diagramIndex
        diagramIndex += 1
        return <Suspense key={key} fallback={<p role="status">Loading diagram renderer…</p>}>
          <MermaidDiagram source={source} index={index} />
        </Suspense>
      }
    }
    const attributes: Record<string, string | boolean> = { key }
    for (const attribute of Array.from(element.attributes)) {
      if (attribute.name === 'class') attributes.className = attribute.value
      else if (attribute.name === 'checked') attributes.defaultChecked = true
      else if (attribute.name === 'disabled') attributes.disabled = true
      else attributes[attribute.name] = attribute.value
    }
    const children = Array.from(element.childNodes).map((child, index) => renderNode(child, `${key}-${index}`))
    return createElement(element.tagName.toLowerCase(), attributes, ...children)
  }

  return Array.from(parsed.childNodes).map((node, index) => renderNode(node, String(index)))
}

export function SanitizedMarkdown({ html }: { html: string }) {
  const content = useMemo(() => renderedMarkdown(html), [html])
  return <div className="markdown-preview">{content}</div>
}
