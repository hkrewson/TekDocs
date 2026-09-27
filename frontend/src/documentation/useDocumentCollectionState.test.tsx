import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach } from 'vitest'
import { useDocumentCollectionState } from './useDocumentCollectionState'

afterEach(() => window.history.replaceState(null, '', '/'))

it('restores valid collection state and writes changes without discarding record parameters', async () => {
  window.history.replaceState(null, '', '/documentation?document=doc-1&doc_q=firewall&doc_category=policy&doc_type=documents&doc_collection=Security&doc_tag=critical&doc_health=stale&doc_order=-updated_at&doc_page=3&doc_library=health')

  const { result } = renderHook(() => useDocumentCollectionState(true, true))

  expect(result.current).toMatchObject({
    query: 'firewall',
    category: 'policy',
    template: 'documents',
    collection: 'Security',
    tag: 'critical',
    health: 'stale',
    ordering: '-updated_at',
    page: 3,
    indexMode: 'health',
  })

  act(() => {
    result.current.setQuery('switch')
    result.current.setPage(1)
  })

  await waitFor(() => {
    const parameters = new URLSearchParams(window.location.search)
    expect(parameters.get('document')).toBe('doc-1')
    expect(parameters.get('doc_q')).toBe('switch')
    expect(parameters.has('doc_page')).toBe(false)
  })
})

it('falls back from unsupported URL values and clears only collection filters', async () => {
  window.history.replaceState(null, '', '/documentation?document=doc-1&doc_category=unknown&doc_health=unknown&doc_order=unknown&doc_page=-4&doc_library=templates')

  const { result } = renderHook(() => useDocumentCollectionState(true, false))

  expect(result.current).toMatchObject({
    category: '',
    health: '',
    ordering: 'title',
    page: 1,
    indexMode: 'browse',
  })

  act(() => result.current.clearFilters())

  await waitFor(() => expect(new URLSearchParams(window.location.search).get('document')).toBe('doc-1'))
})
