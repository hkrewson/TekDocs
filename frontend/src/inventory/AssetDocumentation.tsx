import { useEffect, useRef, useState } from 'react'
import { translate } from '../i18n/localization'
import { SanitizedMarkdown } from '../editor/SanitizedMarkdown'
import type { ContentDocument, ContentDocumentation, InventoryClient } from './api'
import type { WorkspaceContext } from '../workspaces/api'

export function AssetDocumentation({ workspace, assetId, client }: {
  workspace: WorkspaceContext
  assetId: string
  client: InventoryClient
}) {
  const [listing, setListing] = useState<ContentDocumentation | null>(null)
  const [selected, setSelected] = useState<ContentDocument | null>(null)
  const [error, setError] = useState(false)
  const [detailError, setDetailError] = useState(false)
  const [reload, setReload] = useState(0)
  const detailRequest = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!client.listContentDocumentation) return
    const controller = new AbortController()
    detailRequest.current?.abort()
    queueMicrotask(() => {
      if (!controller.signal.aborted) {
        setListing(null)
        setSelected(null)
        setError(false)
      }
    })
    client.listContentDocumentation(workspace, assetId, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setListing(result) })
      .catch(() => { if (!controller.signal.aborted) setError(true) })
    return () => { controller.abort(); detailRequest.current?.abort() }
  }, [assetId, client, reload, workspace])

  function open(contentId: string) {
    if (!client.readContentDocument) return
    const reader = client.readContentDocument.bind(client)
    detailRequest.current?.abort()
    const controller = new AbortController()
    detailRequest.current = controller
    setSelected(null)
    setDetailError(false)
    void reader(workspace, contentId, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setSelected(result) })
      .catch(() => { if (!controller.signal.aborted) setDetailError(true) })
  }

  if (!client.listContentDocumentation || !client.readContentDocument) return null
  if (error) return <p role="alert">{translate('assets.contentDocumentationUnavailable')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('inventory.retryHistory')}</button></p>
  if (!listing) return <p role="status">{translate('assets.contentDocumentationLoading')}</p>
  return <div className="inventory-documents">
    <h3>{translate('assets.contentDocumentation')}</h3>
    {listing.documents.length === 0 ? <p className="empty-state">{translate('assets.noContentDocumentation')}</p> :
      <ul>{listing.documents.map((item, index) => <li key={`${item.id}:${item.relationship}:${item.scope}:${index}`}>
        <button type="button" onClick={() => open(item.id)}>
          <span><strong>{item.title}</strong><small>{translate(`assets.contentScope.${item.scope}`)} · {translate(`assets.contentRelationship.${item.relationship}`)}</small></span>
        </button>
      </li>)}</ul>}
    {detailError && <p role="alert">{translate('assets.contentDocumentUnavailable')}</p>}
    {selected && <section className="retained-document" aria-label={selected.title}>
      <div className="section-heading"><h4>{selected.title}</h4><button type="button" className="secondary-button" onClick={() => setSelected(null)}>{translate('common.close')}</button></div>
      <SanitizedMarkdown html={selected.sanitized_html} />
      {selected.entity_context.length > 0 && <div><h5>{translate('assets.contentAppliesTo')}</h5><ul>{selected.entity_context.map((entity, index) => <li key={`${entity.id}:${entity.relationship}:${index}`}>{entity.display_name} · {translate(`assets.contentRelationship.${entity.relationship}`)}</li>)}</ul></div>}
    </section>}
  </div>
}
