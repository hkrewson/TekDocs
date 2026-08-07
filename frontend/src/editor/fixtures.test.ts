import { markdownFixture } from './fixtures'

describe('supported Markdown fixture', () => {
  it.each([
    ['headings', '# Firewall replacement'],
    ['strong emphasis', '**planned replacement**'],
    ['task lists', '- [ ] Export'],
    ['blockquotes', '> Never copy'],
    ['tables', '| Check | Owner |'],
    ['ordered lists', '1. Verify'],
    ['fenced code', '```shell'],
    ['horizontal rules', '\n---\n'],
    ['stable entity references', 'tekdocs://entity/'],
  ])('contains %s syntax', (_feature, syntax) => {
    expect(markdownFixture).toContain(syntax)
  })
})
