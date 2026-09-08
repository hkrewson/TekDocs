/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const styles = readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8')

const ruleBody = (selector: string) => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = styles.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`))
  return match?.[1] ?? ''
}

describe('shared UI foundations', () => {
  it('declares the application shell and control tokens', () => {
    const requiredTokens = [
      '--space-1: 4px',
      '--space-2: 8px',
      '--space-3: 12px',
      '--space-4: 16px',
      '--space-5: 24px',
      '--space-6: 32px',
      '--radius-small: 6px',
      '--radius-control: 7px',
      '--radius-panel: 8px',
      '--control-height: 36px',
      '--field-height: 38px',
      '--shell-height: 60px',
      '--sidebar-width: 244px',
      '--content-width: 1180px',
      '--shadow-popover:',
      '--shadow-dialog:',
    ]

    for (const token of requiredTokens) expect(styles).toContain(token)
  })

  it('builds reusable controls and surfaces from the shared tokens', () => {
    const expectedTokens: Record<string, string[]> = {
      '.main-content': ['var(--content-width)', 'var(--space-5)', 'var(--space-6)'],
      '.page-header': ['var(--space-5)'],
      '.primary-button': ['var(--control-height)', 'var(--radius-control)'],
      '.secondary-button': ['var(--control-height)', 'var(--radius-control)'],
      '.record-form': ['var(--space-4)', 'var(--radius-panel)', 'var(--shadow-dialog)'],
      '.filter-menu': ['var(--radius-panel)', 'var(--shadow-popover)'],
      '.context-help-popover': ['var(--radius-panel)', 'var(--shadow-popover)'],
      '.auth-panel': ['var(--space-5)', 'var(--radius-panel)'],
      '.auth-form input': ['var(--field-height)', 'var(--radius-control)'],
      '.client-portal-header': ['var(--shell-height)', 'var(--space-5)'],
      '.client-portal-main': ['var(--content-width)', 'var(--space-5)'],
    }

    for (const [selector, tokens] of Object.entries(expectedTokens)) {
      const body = ruleBody(selector)
      expect(body, `${selector} should have a CSS rule`).not.toBe('')
      for (const token of tokens) expect(body).toContain(token)
    }
  })

  it('keeps decorative effects out of shared application controls', () => {
    const sharedSelectors = [
      '.sidebar',
      '.topbar',
      '.primary-button',
      '.secondary-button',
      '.content-section',
      '.record-form',
      '.filter-menu',
      '.auth-panel',
      '.client-portal-header',
    ]

    for (const selector of sharedSelectors) {
      const body = ruleBody(selector)
      expect(body).not.toMatch(/(?:linear|radial)-gradient|backdrop-filter|filter:\s*blur/i)
    }
  })

  it('defines every color and surface token used by the reviewed shells', () => {
    const defined = new Set(Array.from(styles.matchAll(/^\s*(--[a-z0-9-]+)\s*:/gim), (match) => match[1]))
    const used = new Set(Array.from(styles.matchAll(/var\((--[a-z0-9-]+)/g), (match) => match[1]))
    expect([...used].filter((token) => !defined.has(token))).toEqual([])
  })

  it('keeps client portal lifecycle text plain instead of presenting it as a decorative pill', () => {
    const body = ruleBody('.portal-document-list .visibility-label')
    expect(body).toContain('border-radius: 0')
    expect(body).toContain('background: transparent')
    expect(body).not.toContain('999px')
  })
})
