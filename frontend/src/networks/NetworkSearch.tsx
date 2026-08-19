import { useEffect, useState } from 'react'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworkSearchItem, NetworkSearchResult, NetworksClient } from './api'

const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'The network search failed.'

export function NetworkSearch({ workspace, client, query, onOpen }: {
  workspace: WorkspaceContext
  client: NetworksClient
  query: string
  onOpen: (item: NetworkSearchItem) => void
}) {
  const [page, setPage] = useState(1)
  const [result, setResult] = useState<NetworkSearchResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    queueMicrotask(() => { if (!controller.signal.aborted) { setResult(null); setError(null) } })
    client.searchNetwork(workspace, query.trim(), page, controller.signal)
      .then((loaded) => { if (!controller.signal.aborted) setResult(loaded) })
      .catch((caught: unknown) => { if (!controller.signal.aborted) setError(errorMessage(caught)) })
    return () => controller.abort()
  }, [client, page, query, workspace])

  if (error) return <div className="form-error" role="alert">{error}</div>
  if (result === null) return <p role="status">Searching this network workspace…</p>
  return <div className="network-table-wrap" role="group" aria-label={translate('networks.searchTable')} tabIndex={0}>
    <table className="network-table">
      <caption className="sr-only">Search results across network inventory in this workspace</caption>
      <thead><tr><th>Name</th><th>Record type</th><th><span className="sr-only">Actions</span></th></tr></thead>
      <tbody>{result.results.map((item) => <tr key={item.id}><td><strong>{item.name}</strong></td><td>{item.type_label}</td><td><button className="row-action" type="button" onClick={() => onOpen(item)}>{translate('networks.openSection')}</button></td></tr>)}</tbody>
    </table>
    {result.results.length === 0 && <p className="empty-state">No network records match this workspace and search.</p>}
    {result.count > result.page_size && <nav className="pagination" aria-label="Network search pages"><button className="secondary-button" type="button" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>{translate('common.previous')}</button><span>Page {page} · {result.count} records</span><button className="secondary-button" type="button" disabled={!result.has_more} onClick={() => setPage((value) => value + 1)}>{translate('common.next')}</button></nav>}
  </div>
}
