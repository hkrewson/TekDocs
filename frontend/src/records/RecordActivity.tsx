import { useEffect, useRef, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router'
import { AuthRequestError } from '../auth/api'
import { translate } from '../i18n/localization'
import { browserOperationsClient } from '../operations/api'
import type { ActivityResult, OperationsClient } from '../operations/api'
import type { WorkspaceContext } from '../workspaces/api'

export function RecordActivity({ entityId, handoffId, workspace, client = browserOperationsClient, description, emptyLabel, deniedLabel, actionLabels = {}, pageParameter = 'history_page' }: {
  handoffId?: string; pageParameter?: string; entityId: string; description: string; emptyLabel: string; deniedLabel: string; actionLabels?: Record<string, string>; workspace: WorkspaceContext; client?: Pick<OperationsClient, 'activity'>
}) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const requestedPage = Number(params.get(pageParameter) ?? 1)
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  const [reload, setReload] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)
  const focusPage = useRef(false)
  const key = JSON.stringify([workspace.kind, workspace.id, entityId, handoffId, page, reload])
  const [response, setResponse] = useState<{ key: string; result?: ActivityResult; denied?: boolean } | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    client.activity(workspace.kind === 'organization' ? { organizationId: workspace.id } : {}, { entity_id: entityId, ...(handoffId ? { handoff_id: handoffId } : {}), page, page_size: 25 }, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setResponse({ key, result }) })
      .catch((error: unknown) => { if (!controller.signal.aborted) setResponse({ key, denied: error instanceof AuthRequestError && error.status === 403 }) })
    return () => controller.abort()
  }, [entityId, handoffId, workspace.kind, workspace.id, page, key, client])
  const state = response?.key === key ? response : null
  const result = state?.result
  useEffect(() => {
    if (result && focusPage.current) { focusPage.current = false; heading.current?.focus() }
  }, [result])
  function go(next: number) {
    focusPage.current = true
    const query = new URLSearchParams(params)
    if (next === 1) query.delete(pageParameter)
    else query.set(pageParameter, String(next))
    setParams(query, { state: location.state as unknown })
  }
  return <>
    <h2 ref={heading} tabIndex={-1}>{translate('collections.history')}</h2>
    <p>{description}</p>
    {!state ? <p role="status">{translate('collections.historyLoading')}</p> : !result ? <p role="alert">{state.denied ? deniedLabel : translate('inventory.historyLoadFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('inventory.retryHistory')}</button></p> : <>
      {result.results.length ? <ol>{result.results.map((event) => <li key={event.id}><strong>{actionLabels[event.action] ?? event.action.replaceAll('.', ' ')}</strong> · {event.actor_name ?? translate('activity.system')} · <time dateTime={event.occurred_at}>{new Date(event.occurred_at).toLocaleString()}</time></li>)}</ol> : <p>{emptyLabel}</p>}
      <nav className="history-pagination" aria-label={translate('activity.pages')}><button type="button" className="secondary-button" disabled={page === 1} onClick={() => go(page - 1)}>{translate('pagination.previous')}</button><span>{translate('pagination.page', { page })}</span><button type="button" className="secondary-button" disabled={!result.has_more} onClick={() => go(page + 1)}>{translate('pagination.next')}</button></nav>
    </>}
  </>
}
