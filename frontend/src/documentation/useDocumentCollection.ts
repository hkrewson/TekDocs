import { useCallback, useEffect, useRef, useState } from 'react'
import { translate } from '../i18n/localization'
import type { DocumentFilters, DocumentRecord, DocumentScope, DocumentsClient } from './api'

export type LoadedDocumentCollection = {
  key: string
  results: DocumentRecord[]
  count: number
  page: number
  pageSize: number
  hasMore: boolean
  collections: { value: string; count: number }[]
  tags: { value: string; count: number }[]
  health: { value: string; count: number }[]
}

type UseDocumentCollectionOptions = {
  client: DocumentsClient
  filters: DocumentFilters
  requestedDocumentId: string | null
  requestedPublicationId: string | null
  revision: number
  scope: DocumentScope
  scopeKey: string
  onDeepLinkLoaded: (document: DocumentRecord) => void
  onError: (message: string | null) => void
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : translate('documentation.loadFailed')
}

export function useDocumentCollection({
  client,
  filters,
  requestedDocumentId,
  requestedPublicationId,
  revision,
  scope,
  scopeKey,
  onDeepLinkLoaded,
  onError,
}: UseDocumentCollectionOptions) {
  const [loaded, setLoaded] = useState<LoadedDocumentCollection | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const openedDeepLink = useRef<string | null>(null)
  const onDeepLinkLoadedRef = useRef(onDeepLinkLoaded)
  const onErrorRef = useRef(onError)

  useEffect(() => {
    onDeepLinkLoadedRef.current = onDeepLinkLoaded
    onErrorRef.current = onError
  }, [onDeepLinkLoaded, onError])

  useEffect(() => {
    const controller = new AbortController()
    client.list(scope, controller.signal, filters)
      .then(async (result) => {
        if (controller.signal.aborted) return
        setLoaded({
          key: scopeKey,
          results: result.results,
          count: result.count,
          page: result.page ?? filters.page ?? 1,
          pageSize: result.page_size ?? filters.page_size ?? 25,
          hasMore: result.has_more ?? false,
          collections: result.collections ?? [],
          tags: result.tags ?? [],
          health: result.health ?? [],
        })
        setPhase('ready')
        const deepLinkKey = requestedDocumentId ? `${scopeKey}:${requestedDocumentId}:${requestedPublicationId ?? ''}` : null
        let deepLinked = requestedDocumentId ? result.results.find((item) => item.id === requestedDocumentId) : null
        if (requestedDocumentId && deepLinkKey && openedDeepLink.current !== deepLinkKey) {
          if (!deepLinked) {
            try {
              deepLinked = await client.get(scope, requestedDocumentId, controller.signal)
            } catch {
              if (!controller.signal.aborted) onErrorRef.current('That document is not available in this workspace.')
              return
            }
          }
          if (controller.signal.aborted) return
          openedDeepLink.current = deepLinkKey
          onDeepLinkLoadedRef.current(deepLinked)
        }
        onErrorRef.current(null)
      })
      .catch((loadError) => {
        if (!controller.signal.aborted) {
          setPhase('error')
          onErrorRef.current(errorMessage(loadError))
        }
      })
    return () => controller.abort()
  }, [client, filters, requestedDocumentId, requestedPublicationId, revision, scope, scopeKey])

  useEffect(() => {
    if (!requestedDocumentId) openedDeepLink.current = null
  }, [requestedDocumentId])

  const rememberDeepLink = useCallback((documentId: string | null, publicationId = '') => {
    openedDeepLink.current = documentId ? `${scopeKey}:${documentId}:${publicationId}` : null
  }, [scopeKey])

  const updateLoadedDocument = useCallback((documentId: string, update: (document: DocumentRecord) => DocumentRecord) => {
    setLoaded((current) => current ? {
      ...current,
      results: current.results.map((document) => document.id === documentId ? update(document) : document),
    } : current)
  }, [])

  return { loaded, phase, rememberDeepLink, updateLoadedDocument }
}
