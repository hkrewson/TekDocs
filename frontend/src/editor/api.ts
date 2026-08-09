import { browserCsrfToken } from '../auth/api'

type MarkdownPreviewResponse = { html?: unknown }

export async function renderMarkdownPreview(markdown: string, signal?: AbortSignal): Promise<string> {
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
    body: JSON.stringify({ markdown }),
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
