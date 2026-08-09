import { markdownDialectFixture, markdownFixture, markdownRoundTripFixture } from './fixtures'

describe('supported Markdown fixture', () => {
  it.each([
    ['headings', '# UniFi Network Setup Guide'],
    ['strong emphasis', '**Least privilege**'],
    ['unordered lists', '- UniFi Network application'],
    ['blockquotes', '> **Note:**'],
    ['tables', '| VLAN ID | Name |'],
    ['ordered lists', '1. **Least privilege**'],
    ['fenced code', '```xml'],
    ['horizontal rules', '\n---\n'],
    ['links', '[unifi.ui.com](https://unifi.ui.com)'],
  ])('contains %s syntax', (_feature, syntax) => {
    expect(markdownFixture).toContain(syntax)
  })

  it.each([
    ['semantic highlight', '==semantic highlight=='],
    ['strikethrough', '~~Retired guidance~~'],
    ['task lists', '- [x] Export'],
    ['semantic callouts', '> [!WARNING]'],
    ['footnotes', '[^exception]'],
  ])('contains the %s extension contract', (_feature, syntax) => {
    expect(markdownDialectFixture).toContain(syntax)
    expect(markdownRoundTripFixture).toContain(syntax)
  })
})
