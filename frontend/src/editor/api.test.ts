import { vi } from 'vitest'

import { renderMarkdownPreview } from './api'

describe('Markdown preview API', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=preview-csrf; path=/'
  })

  it('sends canonical Markdown through the CSRF-protected server renderer', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({ html: '<p><mark>Check</mark></p>' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ))

    await expect(renderMarkdownPreview('==Check==')).resolves.toBe('<p><mark>Check</mark></p>')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/markdown/render')
    expect(init?.method).toBe('POST')
    expect(init?.credentials).toBe('same-origin')
    expect(init?.body).toBe(JSON.stringify({ markdown: '==Check==' }))
    expect(init?.headers).toEqual(expect.objectContaining({ 'X-CSRFToken': 'preview-csrf' }))
    fetchMock.mockRestore()
  })

  it('does not accept an unreadable preview response', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))

    await expect(renderMarkdownPreview('safe')).rejects.toThrow('unreadable response')
    fetchMock.mockRestore()
  })
})
