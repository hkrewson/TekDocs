import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, Search } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'

import { translate } from '../i18n/localization'
import type { EntityReference, RelationshipsClient } from '../relationships/api'
import type { WorkspaceContext } from '../workspaces/api'

const typeLabels: Record<string, string> = {
  organization: 'Organization', person: 'Person', site: 'Site', location: 'Location', document: 'Document',
  document_attachment: 'File', client_asset: 'Asset', catalog_product: 'Product', catalog_model: 'Model',
  software_license: 'License', commercial_contract: 'Service or contract', credential_reference: 'Credential reference',
  registered_domain: 'Domain', certificate_endpoint: 'Certificate endpoint', data_flow: 'Data flow',
}

function workspacePath(workspace: WorkspaceContext | null, area: string, query = '') {
  const base = workspace ? `/workspaces/organizations/${encodeURIComponent(workspace.id)}/${area}` : `/${area}`
  return query ? `${base}?${query}` : base
}

function resultPath(result: EntityReference, workspace: WorkspaceContext | null) {
  if (result.entity_type === 'organization' && !workspace) return `/workspaces/organizations/${encodeURIComponent(result.id)}/overview`
  if (result.entity_type === 'person') return workspacePath(workspace, 'people')
  if (result.entity_type === 'site' || result.entity_type === 'location') return workspacePath(workspace, 'sites')
  if (result.entity_type === 'document') return workspacePath(workspace, 'documentation', `document=${encodeURIComponent(result.id)}`)
  if (result.entity_type === 'document_attachment') return workspacePath(workspace, 'files', `q=${encodeURIComponent(result.display_name)}`)
  if (result.entity_type === 'client_asset') return workspacePath(workspace, 'assets')
  if (result.entity_type === 'catalog_product' || result.entity_type === 'catalog_model') return workspacePath(workspace, 'products')
  if (result.entity_type === 'software_license') return workspacePath(workspace, 'licenses')
  if (result.entity_type === 'commercial_contract') return workspacePath(workspace, 'services')
  if (result.entity_type === 'credential_reference') return workspacePath(workspace, 'credentials')
  if (result.entity_type === 'registered_domain') return workspacePath(workspace, 'domains')
  if (result.entity_type === 'certificate_endpoint') return workspacePath(workspace, 'certificates', `q=${encodeURIComponent(result.display_name)}`)
  if (result.entity_type === 'data_flow') return workspacePath(workspace, 'compliance')
  if (result.entity_type.startsWith('network_') || result.entity_type === 'wireless_network' || result.entity_type.startsWith('dns_')) return workspacePath(workspace, 'networks')
  return workspacePath(workspace, 'overview')
}

function labelFor(type: string) {
  return typeLabels[type] ?? type.replaceAll('_', ' ').replace(/^./, (value) => value.toUpperCase())
}

export function SearchResults({ workspace, client }: { workspace: WorkspaceContext | null; client: RelationshipsClient }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const query = searchParams.get('q')?.trim() ?? ''
  const [draft, setDraft] = useState(query)
  const [loaded, setLoaded] = useState<{ query: string; results: EntityReference[]; count: number } | null>(null)
  const [failure, setFailure] = useState<{ query: string; message: string } | null>(null)
  const scope = useMemo(() => workspace ? { organizationId: workspace.id } : {}, [workspace])
  const visible = loaded?.query === query ? loaded : null
  const error = failure?.query === query ? failure.message : null

  useEffect(() => {
    if (query.length < 2) return
    const controller = new AbortController()
    client.search(scope, query, undefined, controller.signal)
      .then((response) => { if (!controller.signal.aborted) setLoaded({ query, results: response.results, count: response.count }) })
      .catch((caught: unknown) => { if (!controller.signal.aborted) setFailure({ query, message: caught instanceof Error ? caught.message : translate('search.loadFailed') }) })
    return () => controller.abort()
  }, [client, query, scope])

  function submit(event: React.FormEvent) {
    event.preventDefault()
    const next = new URLSearchParams()
    if (draft.trim()) next.set('q', draft.trim())
    setSearchParams(next)
  }

  return <>
    <header className="page-header"><div><h1>{translate('search.heading')}</h1><p>{translate('search.intro')}</p></div></header>
    <section className="content-section" aria-labelledby="search-results-heading">
      <form className="page-search" role="search" onSubmit={submit}><label htmlFor="workspace-search">{translate('search.label')}</label><div><Search size={17} aria-hidden="true" /><input id="workspace-search" autoFocus type="search" value={draft} maxLength={80} placeholder={translate('search.placeholder')} onChange={(event) => setDraft(event.target.value)} /><button className="primary-button" type="submit">{translate('search.submit')}</button></div></form>
      <div className="section-heading search-results-heading"><div><h2 id="search-results-heading">{query ? translate('search.resultsFor', { query }) : translate('search.results')}</h2>{query && visible && <p>{translate('search.count', { count: visible.count })}</p>}</div></div>
      {error && <p className="form-error" role="alert">{error}</p>}
      {query.length < 2 ? <p className="empty-state">{translate('search.minimum')}</p> : visible === null && !error ? <p role="status">{translate('search.loading')}</p> : visible?.results.length === 0 ? <p className="empty-state">{translate('search.empty')}</p> : <ul className="search-result-list">{visible?.results.map((result) => <li key={result.id}><Link to={resultPath(result, workspace)}><span><strong>{result.display_name}</strong><small>{labelFor(result.entity_type)} · {result.workspace_label}</small></span><ArrowRight size={16} aria-hidden="true" /></Link></li>)}</ul>}
    </section>
  </>
}
