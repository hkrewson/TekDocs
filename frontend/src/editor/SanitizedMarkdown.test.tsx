import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

import { flushDeferredWork } from '../test/flush'
import { SanitizedMarkdown } from './SanitizedMarkdown'
import { sanitizeMarkdownHtml } from './sanitize'

vi.mock('./MermaidDiagram', () => ({
  MermaidDiagram: ({ source }: { source: string }) => <figure><figcaption>Rendered diagram</figcaption><pre>{source}</pre></figure>,
}))

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

  it('hydrates fenced Mermaid source only after sanitized Markdown identifies it', async () => {
    const view = render(<SanitizedMarkdown html={'<pre><code class="language-mermaid">flowchart LR\nA--&gt;B</code></pre>'} />)

    const caption = await screen.findByText('Rendered diagram')
    expect(caption).toBeVisible()
    expect(caption.closest('figure')?.querySelector('pre')).toHaveTextContent('A-->B')

    // The component defers `root.unmount()` to a macrotask so it never unmounts a
    // root mid-render. Unmounting here and letting that callback run keeps teardown
    // inside the test rather than racing the end of the suite.
    view.unmount()
    await flushDeferredWork()
    expect(screen.queryByText('Rendered diagram')).toBeNull()
  })
})
