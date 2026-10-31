import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

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
    expect(view.container.querySelector('code.language-mermaid')).toBeNull()

    view.unmount()
    expect(screen.queryByText('Rendered diagram')).toBeNull()
  })

  it('renders a diagram when saved content replaces an ordinary block', async () => {
    const view = render(<SanitizedMarkdown html="<p>Before editing.</p>" />)

    view.rerender(<SanitizedMarkdown html={'<pre><code class="language-mermaid">flowchart LR\nA--&gt;B</code></pre>'} />)

    expect(await screen.findByText('Rendered diagram')).toBeVisible()
    expect(view.container.querySelector('code.language-mermaid')).toBeNull()
  })
})

it('keeps retained source readable without rerendering it or trusting embedded images', () => {
  const view = render(<SanitizedMarkdown retainedDiagrams={[]} html={'<figure class="mermaid-diagram-export"><figcaption>Retained route</figcaption><img src="data:image/svg+xml;base64,bad" onerror="alert(1)"><details><summary>Accessible diagram source</summary><pre><code class="language-mermaid">flowchart LR\nA--&gt;B</code></pre></details></figure><img src="https://untrusted.example.invalid/tracker">'} />)
  expect(screen.getByText('Retained route')).toBeVisible()
  expect(screen.getByText('Accessible diagram source')).toBeVisible()
  expect(view.container.querySelector('code.language-mermaid')).toHaveTextContent('A-->B')
  expect(screen.queryByText('Rendered diagram')).not.toBeInTheDocument()
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
})
