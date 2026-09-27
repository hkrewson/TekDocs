import { renderHook, waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import type { DocumentFilters, DocumentRecord, DocumentsClient } from './api'
import { useDocumentCollection } from './useDocumentCollection'

const firstDocument = { id: 'doc-first', title: 'First result' } as DocumentRecord
const secondDocument = { id: 'doc-second', title: 'Second result' } as DocumentRecord

function options(client: DocumentsClient, filters: DocumentFilters, onDeepLinkLoaded = vi.fn(), onError = vi.fn()) {
  return {
    client,
    filters,
    requestedDocumentId: null,
    requestedPublicationId: null,
    revision: 0,
    scope: {},
    scopeKey: 'msp',
    onDeepLinkLoaded,
    onError,
  }
}

it('ignores a stale collection response after its request is canceled', async () => {
  let resolveFirst: ((value: { results: DocumentRecord[]; count: number }) => void) | undefined
  const firstRequest = new Promise<{ results: DocumentRecord[]; count: number }>((resolve) => { resolveFirst = resolve })
  const list = vi.fn((_scope: object, _signal: AbortSignal, filters?: DocumentFilters) => filters?.q === 'first'
    ? firstRequest
    : Promise.resolve({ results: [secondDocument], count: 1 }))
  const client = { list } as unknown as DocumentsClient
  const firstFilters = { q: 'first', page: 1, page_size: 25 }
  const secondFilters = { q: 'second', page: 1, page_size: 25 }

  const { result, rerender } = renderHook(({ filters }) => useDocumentCollection(options(client, filters)), { initialProps: { filters: firstFilters } })
  rerender({ filters: secondFilters })

  await waitFor(() => expect(result.current.loaded?.results).toEqual([secondDocument]))
  resolveFirst?.({ results: [firstDocument], count: 1 })
  await waitFor(() => expect(result.current.loaded?.results).toEqual([secondDocument]))
})

it('loads an authorized off-page record without taking ownership of selection', async () => {
  const onDeepLinkLoaded = vi.fn()
  const onError = vi.fn()
  const get = vi.fn().mockResolvedValue(firstDocument)
  const client = {
    list: vi.fn().mockResolvedValue({ results: [], count: 50, page: 1, page_size: 25, has_more: true }),
    get,
  } as unknown as DocumentsClient

  renderHook(() => useDocumentCollection({
    ...options(client, { page: 1, page_size: 25 }, onDeepLinkLoaded, onError),
    requestedDocumentId: firstDocument.id,
  }))

  await waitFor(() => expect(onDeepLinkLoaded).toHaveBeenCalledWith(firstDocument))
  expect(get).toHaveBeenCalledWith({}, firstDocument.id, expect.any(AbortSignal))
  expect(onError).toHaveBeenLastCalledWith(null)
})
