import createClient, { type Middleware } from 'openapi-fetch'

import type { paths } from '../generated/api-v1'

const IDEMPOTENCY_KEY = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,199}$/

function csrfToken(): string | null {
  const value = document.cookie
    .split('; ')
    .find((part) => part.startsWith('csrftoken='))
    ?.slice('csrftoken='.length)
  return value ? decodeURIComponent(value) : null
}

const sameOriginSession: Middleware = {
  onRequest({ request }) {
    request.headers.set('Accept', 'application/json')
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method)) {
      const token = csrfToken()
      if (token) request.headers.set('X-CSRFToken', token)
    }
    return request
  },
}

export function createTekDocsApiClient(baseUrl = '') {
  const client = createClient<paths>({ baseUrl, credentials: 'same-origin' })
  client.use(sameOriginSession)
  return client
}

export function idempotencyHeaders(key: string): { 'Idempotency-Key': string } {
  if (!IDEMPOTENCY_KEY.test(key)) {
    throw new Error('Idempotency keys must contain 8–200 allowed ASCII characters.')
  }
  return { 'Idempotency-Key': key }
}
