import { browserCsrfToken } from '../auth/api'

type MarkdownPreviewResponse = { html?: unknown }
type DiagramPreviewResponse = { svg?: unknown; title?: unknown; description?: unknown; renderer_version?: unknown }

export type RenderedDiagramPreview = { svg: string; title: string; description: string; rendererVersion: string }

export async function renderMarkdownPreview(markdown: string, organizationId?: string, documentId?: string, signal?: AbortSignal): Promise<string> {
  const csrfToken = browserCsrfToken()
  if (!csrfToken) throw new Error('The browser security token is unavailable. Refresh and try again.')
  const response = await fetch('/api/v1/markdown/render', {
    method: 'POST',
    credentials: 'same-origin',
    signal,
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    },
    body: JSON.stringify({ markdown, organization_id: organizationId ?? null, document_id: documentId ?? null }),
  })
  if (!response.ok) {
    throw new Error(response.status === 400
      ? 'This Markdown is too large or could not be rendered.'
      : 'The secure preview could not be loaded.')
  }
  const payload = await response.json() as MarkdownPreviewResponse
  if (typeof payload.html !== 'string') throw new Error('The preview service returned an unreadable response.')
  return payload.html
}

export async function renderDiagramPreview(source: string, signal?: AbortSignal): Promise<RenderedDiagramPreview> {
  const csrfToken = browserCsrfToken()
  if (!csrfToken) throw new Error('The browser security token is unavailable. Refresh and try again.')
  const response = await fetch('/api/v1/diagrams/preview', {
    method: 'POST',
    credentials: 'same-origin',
    signal,
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    },
    body: JSON.stringify({ source }),
  })
  if (!response.ok) throw new Error('The isolated diagram renderer could not produce this preview.')
  const payload = await response.json() as DiagramPreviewResponse
  if (typeof payload.svg !== 'string' || typeof payload.title !== 'string'
    || typeof payload.description !== 'string' || typeof payload.renderer_version !== 'string') {
    throw new Error('The diagram preview service returned an unreadable response.')
  }
  return { svg: payload.svg, title: payload.title, description: payload.description, rendererVersion: payload.renderer_version }
}
