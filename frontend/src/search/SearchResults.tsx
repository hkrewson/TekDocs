import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, Search } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { CollectionPagination } from '../CollectionPagination'
import { FilterMenu } from '../FilterMenu'

import { formatInstantDate, translate } from '../i18n/localization'
import type { MessageId } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type {
  WorkspaceSearchClient,
  WorkspaceSearchResult,
  WorkspaceSearchResultType,
} from './api'
import { workspaceSearchResultTypes } from './api'

const resultTypeLabelIds: Record<WorkspaceSearchResultType, MessageId> = {
  organization: 'search.type.organization', person: 'search.type.person', site: 'search.type.site', location: 'search.type.location', document: 'search.type.document', file: 'search.type.file', asset: 'search.type.asset', product: 'search.type.product', model: 'search.type.model', license: 'search.type.license', service: 'search.type.service', credential_reference: 'search.type.credentialReference', domain: 'search.type.domain', certificate: 'search.type.certificate', network: 'search.type.network', data_flow: 'search.type.dataFlow',
  external_ticket: 'search.type.externalTicket',
}

const resultTypeSingularLabelIds: Record<WorkspaceSearchResultType, MessageId> = {
  organization: 'search.typeSingle.organization', person: 'search.typeSingle.person', site: 'search.typeSingle.site', location: 'search.typeSingle.location', document: 'search.typeSingle.document', file: 'search.typeSingle.file', asset: 'search.typeSingle.asset', product: 'search.typeSingle.product', model: 'search.typeSingle.model', license: 'search.typeSingle.license', service: 'search.typeSingle.service', credential_reference: 'search.typeSingle.credentialReference', domain: 'search.typeSingle.domain', certificate: 'search.typeSingle.certificate', network: 'search.typeSingle.network', data_flow: 'search.typeSingle.dataFlow',
  external_ticket: 'search.typeSingle.externalTicket',
}

function resultKey(query: string, resultType: string, page: number, pageSize: number, revision: number) {
  return `${query}\u0000${resultType}\u0000${page}\u0000${pageSize}\u0000${revision}`
}

function pageFrom(value: string | null) {
  const page = Number(value ?? '1')
  return Number.isInteger(page) && page > 0 ? page : 1
}

function pageSizeFrom(value: string | null): 25 | 50 | 100 {
  const pageSize = Number(value)
  return pageSize === 50 || pageSize === 100 ? pageSize : 25
}

function searchResultType(value: string | null): WorkspaceSearchResultType | '' {
  return workspaceSearchResultTypes.includes(value as WorkspaceSearchResultType)
    ? value as WorkspaceSearchResultType
    : ''
}

function reviewLabel(value: string | null) {
  if (!value) return null
  const labels: Record<string, MessageId> = {
    unreviewed: 'search.review.unreviewed', pending: 'search.review.pending', approved: 'search.review.approved', changes_requested: 'search.review.changesRequested',
  }
  return labels[value] ? translate(labels[value]) : null
}

export function SearchResults({ workspace, client }: {
  workspace: WorkspaceContext | null
  client: WorkspaceSearchClient
}) {
  const [searchParams, setSearchParams] = useSearchParams()
  const query = searchParams.get('q')?.trim() ?? ''
  const resultType = searchResultType(searchParams.get('type'))
  const page = pageFrom(searchParams.get('page'))
  const pageSize = pageSizeFrom(searchParams.get('page_size'))
  const [revision, setRevision] = useState(0)
  const [draft, setDraft] = useState(query)
  const [loaded, setLoaded] = useState<{ key: string; result: WorkspaceSearchResult } | null>(null)
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null)
  const scope = useMemo(() => workspace ? { organizationId: workspace.id } : {}, [workspace])
  const key = resultKey(query, resultType, page, pageSize, revision)
  const visible = loaded?.key === key ? loaded.result : null
  const error = failure?.key === key ? failure.message : null

  useEffect(() => {
    if (query.length < 2) return
    const controller = new AbortController()
    client.search(scope, query, resultType, page, pageSize, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setLoaded({ key, result })
          setFailure(null)
        }
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setFailure({ key, message: caught instanceof Error ? caught.message : translate('search.loadFailed') })
        }
      })
    return () => controller.abort()
  }, [client, key, page, pageSize, query, resultType, scope])

  function updateParameters(nextQuery: string, nextType: WorkspaceSearchResultType | '', nextPage = 1, nextPageSize = pageSize) {
    const next = new URLSearchParams()
    if (nextQuery.trim()) next.set('q', nextQuery.trim())
    if (nextType) next.set('type', nextType)
    if (nextPage > 1) next.set('page', String(nextPage))
    if (nextPageSize !== 25) next.set('page_size', String(nextPageSize))
    setSearchParams(next)
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    updateParameters(draft, resultType)
  }

  const facetCounts = new Map(visible?.facets.map((facet) => [facet.value, facet.count]) ?? [])
  return <>
    <header className="page-header"><div><h1>{translate('search.heading')}</h1><p>{translate('search.intro')}</p></div></header>
    <section className="content-section" aria-labelledby="search-results-heading">
      <form className="page-search" role="search" onSubmit={submit}>
        <label htmlFor="workspace-search">{translate('search.label')}</label>
        <div><Search size={17} aria-hidden="true" /><input id="workspace-search" autoFocus type="search" value={draft} maxLength={80} placeholder={translate('search.placeholder')} onChange={(event) => setDraft(event.target.value)} /><button className="primary-button" type="submit">{translate('search.submit')}</button></div>
      </form>
      <div className="search-controls"><FilterMenu groups={[{
        kind: 'choices',
        label: translate('search.resultType'),
        value: resultType,
        choices: [
          { value: '', label: visible ? translate('search.allResultsCount', { count: visible.facets.reduce((count, facet) => count + facet.count, 0) }) : translate('search.allResults') },
          ...workspaceSearchResultTypes.map((value) => ({ value, label: facetCounts.has(value) ? translate('search.typeCount', { label: translate(resultTypeLabelIds[value]), count: facetCounts.get(value) ?? 0 }) : translate(resultTypeLabelIds[value]) })),
        ],
        onChange: (value) => updateParameters(query, searchResultType(value)),
      }]} activeCount={resultType ? 1 : 0} onClear={() => updateParameters(query, '')} menuLabel={translate('search.filters')} />
        <label className="collection-page-size">{translate('collections.pageSize')}<select value={pageSize} onChange={(event) => updateParameters(query, resultType, 1, Number(event.target.value) as 25 | 50 | 100)}><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option></select></label>
      </div>
      {resultType && <div className="collection-active-filters"><button type="button" className="row-action" onClick={() => updateParameters(query, '')}>{translate('search.resultType')}: {translate(resultTypeSingularLabelIds[resultType])} ×</button></div>}
      <div className="section-heading search-results-heading"><div><h2 id="search-results-heading">{query ? translate('search.resultsFor', { query }) : translate('search.results')}</h2>{query && visible && <p>{visible.truncated ? translate('search.countLimited', { count: visible.count }) : translate('search.count', { count: visible.count })}</p>}</div></div>
      {error && <div role="alert"><p className="form-error">{error}</p><button className="secondary-button" type="button" onClick={() => setRevision((value) => value + 1)}>{translate('common.retry')}</button></div>}
      {query.length < 2
        ? <p className="empty-state">{translate('search.minimum')}</p>
        : visible === null && !error
          ? <p role="status">{translate('search.loading')}</p>
          : visible?.results.length === 0
            ? <p className="empty-state">{translate('search.empty')}</p>
            : <>
              <ul className="search-result-list">
                {visible?.results.map((result) => <li key={result.id}>
                  {result.result_type === 'external_ticket' ? <a href={result.target} target="_blank" rel="noreferrer">
                    <span>
                      <strong>{result.title}</strong>
                      {result.excerpt && <span className="search-result-excerpt">{result.excerpt}</span>}
                      <small>{reviewLabel(result.review_state) ? translate('search.resultMetadataReviewed', { type: translate(resultTypeSingularLabelIds[result.result_type]), workspace: result.workspace_label, updated: formatInstantDate(result.updated_at), review: reviewLabel(result.review_state) ?? '' }) : translate('search.resultMetadata', { type: translate(resultTypeSingularLabelIds[result.result_type]), workspace: result.workspace_label, updated: formatInstantDate(result.updated_at) })}</small>
                    </span>
                    <ArrowRight size={16} aria-hidden="true" />
                  </a> : <Link to={result.target}>
                    <span>
                      <strong>{result.title}</strong>
                      {result.excerpt && <span className="search-result-excerpt">{result.excerpt}</span>}
                      <small>{reviewLabel(result.review_state) ? translate('search.resultMetadataReviewed', { type: translate(resultTypeSingularLabelIds[result.result_type]), workspace: result.workspace_label, updated: formatInstantDate(result.updated_at), review: reviewLabel(result.review_state) ?? '' }) : translate('search.resultMetadata', { type: translate(resultTypeSingularLabelIds[result.result_type]), workspace: result.workspace_label, updated: formatInstantDate(result.updated_at) })}</small>
                    </span>
                    <ArrowRight size={16} aria-hidden="true" />
                  </Link>}
                </li>)}
              </ul>
              {visible && <CollectionPagination label={translate('search.results')} page={page} pageSize={pageSize} count={visible.count} hasMore={visible.has_more} onPageChange={(nextPage) => updateParameters(query, resultType, nextPage)} />}
            </>}
    </section>
  </>
}
