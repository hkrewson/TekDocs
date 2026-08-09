import { useMemo } from 'react'

import { sanitizeMarkdownHtml } from './sanitize'

export function SanitizedMarkdown({ html }: { html: string }) {
  const sanitized = useMemo(() => sanitizeMarkdownHtml(html), [html])
  return <div className="markdown-preview" dangerouslySetInnerHTML={{ __html: sanitized }} />
}
