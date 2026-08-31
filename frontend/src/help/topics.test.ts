import { helpTopicForPath, helpTopicSlugs, helpTopicUrl, WIKI_BASE_URL } from './topics'

describe('contextual help topics', () => {
  it('normalizes MSP and organization workspace routes to the same stable topic', () => {
    expect(helpTopicForPath('/documentation').slug).toBe('Documentation')
    expect(helpTopicForPath('/staff').slug).toBe('People-and-access')
    expect(helpTopicForPath('/workspaces/organizations/123/documentation').slug).toBe('Documentation')
    expect(helpTopicForPath('/workspaces/organizations/123/recycle_bin').slug).toBe('Recycle-bin')
    expect(helpTopicForPath('/invoices').slug).toBe('Invoices')
    expect(helpTopicForPath('/accounting').slug).toBe('Invoices')
    expect(helpTopicForPath('/tickets').slug).toBe('Workspaces-and-organizations')
  })

  it('falls back safely and creates only same-Wiki topic URLs', () => {
    const topic = helpTopicForPath('/not-a-real-area')
    expect(topic.slug).toBe('Workspaces-and-organizations')
    expect(helpTopicUrl(topic)).toBe(`${WIKI_BASE_URL}/Workspaces-and-organizations`)
    expect(helpTopicSlugs).not.toContain('')
  })
})
