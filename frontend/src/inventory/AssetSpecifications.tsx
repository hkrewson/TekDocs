import { useState } from 'react'
import { FileText, CheckCircle2 } from 'lucide-react'
import { translate } from '../i18n/localization'
import { SanitizedMarkdown } from '../editor/SanitizedMarkdown'
import type { WorkspaceContext } from '../workspaces/api'
import type { ClientAsset, AssetDocument, InventoryClient } from './api'

export function AssetSpecifications({ selected, workspace, client }: { selected: ClientAsset; workspace: WorkspaceContext; client: InventoryClient }) {
  const [document, setDocument] = useState<(AssetDocument & { sanitized_html: string }) | null>(null)
  const [error, setError] = useState<string | null>(null)
  async function openDocument(asset: ClientAsset, item: AssetDocument) {
    setError(null)
    try { setDocument(await client.loadDocument(workspace, asset.id, item.publication_id)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : translate('assets.documentLoadFailed')) }
  }
  return <>{error && <p role="alert">{error}</p>}<dl className="inventory-provenance"><div><dt>Model revision</dt><dd>{selected.model_revision}</dd></div><div><dt>Specification version</dt><dd>{selected.specification_version}</dd></div><div><dt>{translate('assets.sourceCheck')}</dt><dd><code>{selected.provenance_checksum}</code></dd></div></dl><h3>{translate('assets.savedSpecifications')}</h3><dl className="catalog-specification-list">{Object.entries(selected.specifications).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{typeof value === 'boolean' ? value ? 'Yes' : 'No' : String(value)}</dd></div>)}</dl><div className="inventory-documents"><h3>Product documentation</h3>{selected.documents.length === 0 ? <p className="empty-state">{translate('assets.noProductDocuments')}</p> : <ul>{selected.documents.map((item) => <li key={item.publication_id}><button type="button" onClick={() => { void openDocument(selected, item) }}><FileText size={16} /><span><strong>{item.title}</strong><small>{translate('collections.publishedDocument', { category: item.category, date: new Date(item.published_at).toLocaleDateString() })}</small></span><CheckCircle2 size={15} aria-label="Signature verified" /></button></li>)}</ul>}</div>{document && <section className="retained-document"><div className="section-heading"><div><h3>{document.title}</h3><p>{document.reason}</p></div><button type="button" className="secondary-button" onClick={() => setDocument(null)}>{translate('common.close')}</button></div><SanitizedMarkdown html={document.sanitized_html} />{document.artifacts.map((artifact) => <a className="secondary-button" key={artifact.id} href={client.artifactUrl(workspace, selected.id, document.publication_id, artifact.id)}>{artifact.kind === 'pdf' ? translate('assets.downloadPublishedPdf') : `Download ${artifact.filename}`}</a>)}</section>}</>
}
