import { vi } from 'vitest'

import { renderDiagramPreview, renderMarkdownPreview } from './api'

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
    expect(init?.body).toBe(JSON.stringify({ markdown: '==Check==', organization_id: null, document_id: null }))
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

  it('requests a CSRF-protected isolated diagram preview', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      svg: '<svg xmlns="http://www.w3.org/2000/svg"/>',
      title: 'Network path',
      description: 'A path',
      renderer_version: '@mermaid-js/mermaid-cli@11.16.0',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    await expect(renderDiagramPreview('flowchart LR\nA-->B')).resolves.toEqual({
      svg: '<svg xmlns="http://www.w3.org/2000/svg"/>',
      title: 'Network path',
      description: 'A path',
      rendererVersion: '@mermaid-js/mermaid-cli@11.16.0',
    })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/diagrams/preview')
    expect(init?.method).toBe('POST')
    expect(init?.credentials).toBe('same-origin')
    expect(init?.body).toBe(JSON.stringify({ source: 'flowchart LR\nA-->B' }))
    expect(init?.headers).toEqual(expect.objectContaining({ 'X-CSRFToken': 'preview-csrf' }))
    fetchMock.mockRestore()
  })
})
