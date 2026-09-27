import { useEffect, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { DocumentCategory, DocumentFilters, DocumentHealthStatus } from './api'

export type DocumentIndexMode = 'browse' | 'health' | 'templates'
export type DocumentTemplateFilter = 'all' | 'documents' | 'templates'

type DocumentCollectionState = {
  category: DocumentCategory | ''
  collection: string
  health: DocumentHealthStatus | ''
  indexMode: DocumentIndexMode
  ordering: NonNullable<DocumentFilters['ordering']>
  page: number
  query: string
  tag: string
  template: DocumentTemplateFilter
  setCategory: Dispatch<SetStateAction<DocumentCategory | ''>>
  setCollection: Dispatch<SetStateAction<string>>
  setHealth: Dispatch<SetStateAction<DocumentHealthStatus | ''>>
  setIndexMode: Dispatch<SetStateAction<DocumentIndexMode>>
  setOrdering: Dispatch<SetStateAction<NonNullable<DocumentFilters['ordering']>>>
  setPage: Dispatch<SetStateAction<number>>
  setQuery: Dispatch<SetStateAction<string>>
  setTag: Dispatch<SetStateAction<string>>
  setTemplate: Dispatch<SetStateAction<DocumentTemplateFilter>>
  clearFilters: () => void
}

const categories: DocumentCategory[] = ['general', 'policy', 'procedure', 'guide', 'reference']
const healthStates: DocumentHealthStatus[] = ['current', 'stale', 'unreviewed', 'unowned', 'pending', 'changes_requested']
const orderings: NonNullable<DocumentFilters['ordering']>[] = ['title', '-title', 'updated_at', '-updated_at', 'category', '-category']

function initialParameters() {
  return new URLSearchParams(typeof window === 'undefined' ? '' : window.location.search)
}

export function useDocumentCollectionState(urlManaged: boolean, workspaceAvailable: boolean): DocumentCollectionState {
  const [parameters] = useState(initialParameters)
  const [query, setQuery] = useState(() => urlManaged ? parameters.get('doc_q') ?? '' : '')
  const [category, setCategory] = useState<DocumentCategory | ''>(() => {
    const value = parameters.get('doc_category') as DocumentCategory | null
    return urlManaged && value && categories.includes(value) ? value : ''
  })
  const [template, setTemplate] = useState<DocumentTemplateFilter>(() => {
    const value = parameters.get('doc_type') as DocumentTemplateFilter | null
    return urlManaged && value && ['documents', 'templates'].includes(value) ? value : 'all'
  })
  const [collection, setCollection] = useState(() => urlManaged ? parameters.get('doc_collection') ?? '' : '')
  const [tag, setTag] = useState(() => urlManaged ? parameters.get('doc_tag') ?? '' : '')
  const [health, setHealth] = useState<DocumentHealthStatus | ''>(() => {
    const value = parameters.get('doc_health') as DocumentHealthStatus | null
    return urlManaged && value && healthStates.includes(value) ? value : ''
  })
  const [ordering, setOrdering] = useState<NonNullable<DocumentFilters['ordering']>>(() => {
    const value = parameters.get('doc_order') as NonNullable<DocumentFilters['ordering']> | null
    return urlManaged && value && orderings.includes(value) ? value : 'title'
  })
  const [page, setPage] = useState(() => {
    const value = Number(parameters.get('doc_page'))
    return urlManaged && Number.isInteger(value) && value > 0 ? value : 1
  })
  const [indexMode, setIndexMode] = useState<DocumentIndexMode>(() => {
    if (!urlManaged) return 'browse'
    if (parameters.get('doc_library') === 'templates' && workspaceAvailable) return 'templates'
    return parameters.get('doc_library') === 'health' ? 'health' : 'browse'
  })

  useEffect(() => {
    if (!urlManaged) return
    const next = new URLSearchParams(window.location.search)
    const values: Record<string, string> = {
      doc_library: indexMode === 'templates' ? 'templates' : indexMode === 'health' ? 'health' : '',
      doc_q: query,
      doc_category: category,
      doc_type: template === 'all' ? '' : template,
      doc_collection: collection,
      doc_tag: tag,
      doc_health: health,
      doc_order: ordering === 'title' ? '' : ordering,
      doc_page: page === 1 ? '' : String(page),
    }
    Object.entries(values).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key))
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${next.size ? `?${next}` : ''}${window.location.hash}`)
  }, [category, collection, health, indexMode, ordering, page, query, tag, template, urlManaged])

  const clearFilters = () => {
    setCategory('')
    setCollection('')
    setTag('')
    setHealth('')
    setTemplate('all')
    setPage(1)
  }

  return {
    category,
    collection,
    health,
    indexMode,
    ordering,
    page,
    query,
    tag,
    template,
    setCategory,
    setCollection,
    setHealth,
    setIndexMode,
    setOrdering,
    setPage,
    setQuery,
    setTag,
    setTemplate,
    clearFilters,
  }
}
