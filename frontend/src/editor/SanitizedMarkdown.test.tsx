import { render, screen } from '@testing-library/react'

import { SanitizedMarkdown } from './SanitizedMarkdown'
import { sanitizeMarkdownHtml } from './sanitize'

describe('sanitized Markdown preview', () => {
  it('keeps the supported semantic output', () => {
    render(<SanitizedMarkdown html={'<p><mark>Check</mark> <a href="tekdocs://entity/123">Router</a></p><blockquote class="callout callout-warning" data-callout="warning"><strong class="callout-title">Warning</strong></blockquote>'} />)

    expect(screen.getByText('Check').tagName).toBe('MARK')
    expect(screen.getByRole('link', { name: 'Router' })).toHaveAttribute('href', 'tekdocs://entity/123')
    expect(document.querySelector('blockquote')).toHaveAttribute('data-callout', 'warning')
  })

  it('removes executable markup, unsafe URLs, styles, and event handlers', () => {
    const sanitized = sanitizeMarkdownHtml('<script>alert(1)</script><a href="javascript:alert(1)" style="position:fixed" onclick="alert(1)">Unsafe</a><iframe srcdoc="bad"></iframe>')

    expect(sanitized).toBe('<a>Unsafe</a>')
  })
})
