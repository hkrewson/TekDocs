import { render, screen } from '@testing-library/react'

import { MarkdownHelp } from './MarkdownHelp'

it('keeps the internally hosted help aligned with the supported Markdown contract', () => {
  render(<MarkdownHelp />)
  for (const syntax of [
    '**important**', '*emphasis*', '~~retired~~', '==verify this==', '`interface ge-0/0/1`',
    '## Preparation', '- Record the serial number', '1. Export the configuration',
    '- [ ] Confirm the maintenance window', '> Original vendor guidance', '[!WARNING]',
    '```powershell', '| Port | Purpose |', '---', '[^1]',
  ]) expect(screen.getAllByText((content) => content.includes(syntax)).length).toBeGreaterThan(0)
  expect(screen.getByText(/Raw HTML, MDX, scripts, inline styles, and author-supplied CSS are not supported/)).toBeInTheDocument()
})
