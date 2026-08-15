const inlineSyntax = [
  ['Bold', '**important**'],
  ['Italic', '*emphasis*'],
  ['Strikethrough', '~~retired~~'],
  ['Semantic highlight', '==verify this=='],
  ['Inline code', '`interface ge-0/0/1`'],
  ['Link', '[Vendor documentation](https://example.com)'],
]

const blockSyntax = [
  ['Heading', '## Preparation'],
  ['Bulleted list', '- Record the serial number'],
  ['Numbered list', '1. Export the configuration'],
  ['Task list', '- [ ] Confirm the maintenance window'],
  ['Quote', '> Original vendor guidance'],
  ['Callout', '> [!WARNING]\n> Rebooting disconnects the site.'],
  ['Code block', '```powershell\nGet-NetAdapter\n```'],
  ['Mermaid diagram', '```mermaid\nflowchart LR\naccTitle: Network path\nA[User] --> B[Firewall]\n```'],
  ['Table', '| Port | Purpose |\n| --- | --- |\n| 1 | WAN |'],
  ['Divider', '---'],
  ['Footnote', 'Documented exception.[^1]\n\n[^1]: Approval details.'],
]

export function MarkdownHelp() {
  return (
    <div className="markdown-help" aria-labelledby="markdown-help-heading">
      <div className="markdown-help-intro">
        <h2 id="markdown-help-heading">TekDocs Markdown</h2>
        <p>The visual editor and raw source produce the same canonical Markdown. Highlight communicates relevance; warnings and risks belong in callouts.</p>
      </div>
      <section aria-labelledby="inline-formatting-heading">
        <h3 id="inline-formatting-heading">Inline formatting</h3>
        <div className="markdown-help-table" role="table" aria-label="Inline Markdown syntax">
          {inlineSyntax.map(([name, syntax]) => (
            <div role="row" key={name}><strong role="cell">{name}</strong><code role="cell">{syntax}</code></div>
          ))}
        </div>
      </section>
      <section aria-labelledby="block-formatting-heading">
        <h3 id="block-formatting-heading">Blocks and technical content</h3>
        <div className="markdown-help-table" role="table" aria-label="Block Markdown syntax">
          {blockSyntax.map(([name, syntax]) => (
            <div role="row" key={name}><strong role="cell">{name}</strong><code role="cell">{syntax}</code></div>
          ))}
        </div>
      </section>
      <section className="markdown-help-safety" aria-labelledby="safe-markdown-heading">
        <h3 id="safe-markdown-heading">Portable and safe by design</h3>
        <p>Raw HTML, MDX, scripts, inline styles, and author-supplied CSS are not supported. Mermaid diagrams use strict local rendering and retain their source as an accessible fallback. TekDocs controls colors and presentation so documents remain readable in dark mode, print, PDF, and other Markdown tools.</p>
      </section>
    </div>
  )
}
