import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, FileText, Plus, Search } from 'lucide-react'
import { SanitizedMarkdown } from '../editor/SanitizedMarkdown'
import type { WorkspaceContext } from '../workspaces/api'
import type { AssetDocument, ClientAsset, InventoryClient, ModelChoice } from './api'
import { HardwareLifecycle } from './HardwareLifecycle'
import { SoftwareInstallation } from './SoftwareInstallation'

export function Assets({ workspace, client }: { workspace: WorkspaceContext; client: InventoryClient }) {
  const [assets, setAssets] = useState<ClientAsset[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [canManage, setCanManage] = useState(false)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [creating, setCreating] = useState(false)
  const [modelQuery, setModelQuery] = useState('')
  const [modelChoices, setModelChoices] = useState<ModelChoice[]>([])
  const [modelId, setModelId] = useState('')
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [document, setDocument] = useState<(AssetDocument & { sanitized_html: string }) | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    client.listAssets(workspace, controller.signal)
      .then((result) => { setAssets(result.results); setCanManage(result.can_manage); setPhase('ready') })
      .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client, workspace])

  useEffect(() => {
    if (!creating) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.listModelChoices(workspace, modelQuery, controller.signal)
        .then((result) => setModelChoices(result.results))
        .catch(() => { if (!controller.signal.aborted) setError('Supplier models could not be loaded.') })
    }, 150)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, creating, modelQuery, workspace])

  const selected = useMemo(() => assets.find((asset) => asset.id === selectedId) ?? assets[0], [assets, selectedId])
  const choice = modelChoices.find((item) => item.id === modelId)

  async function createAsset() {
    if (!modelId) return
    setSaving(true); setError(null)
    try {
      const created = await client.createAsset(workspace, modelId, name)
      setAssets((current) => [...current, created])
      setSelectedId(created.id); setCreating(false); setModelId(''); setName('')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The asset could not be created.') }
    finally { setSaving(false) }
  }

  async function openDocument(asset: ClientAsset, item: AssetDocument) {
    setError(null)
    try { setDocument(await client.loadDocument(workspace, asset.id, item.publication_id)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'The retained publication could not be loaded.') }
  }

  function updateHardware(assetId: string, hardware: NonNullable<ClientAsset['hardware']>) {
    setAssets((current) => current.map((asset) => asset.id === assetId ? { ...asset, hardware } : asset))
  }
  function updateSoftware(assetId: string, software_installation: NonNullable<ClientAsset['software_installation']>) {
    setAssets((current) => current.map((asset) => asset.id === assetId ? { ...asset, software_installation } : asset))
  }

  return <>
    <header className="page-header"><div><h1>Assets</h1><p>Client-owned records created from exact supplier models and retained documentation.</p></div>{canManage && <button type="button" className="primary-button" onClick={() => setCreating(true)}><Plus size={16} />New asset</button>}</header>
    {error && <div className="form-message error" role="alert">{error}</div>}
    {phase === 'loading' && <section className="content-section" role="status">Loading client assets…</section>}
    {phase === 'error' && <section className="content-section workspace-error" role="alert"><h2>Assets unavailable</h2><p>The client inventory could not be loaded.</p></section>}
    {phase === 'ready' && <div className="inventory-layout"><section className="content-section inventory-index">{assets.length === 0 ? <p className="empty-state">No assets have been created for this client.</p> : <ul className="inventory-list">{assets.map((asset) => <li key={asset.id}><button type="button" className={selected?.id === asset.id ? 'selected' : ''} onClick={() => { setSelectedId(asset.id); setDocument(null) }}><strong>{asset.name}</strong><span>{asset.supplier_name} · {asset.model_number}</span></button></li>)}</ul>}</section><section className="content-section inventory-detail">{selected ? <><div className="section-heading"><div><h2>{selected.name}</h2><p>{selected.supplier_name} / {selected.product_name} / {selected.model_name}</p></div><span>{selected.kind}</span></div><dl className="inventory-provenance"><div><dt>Model revision</dt><dd>{selected.model_revision}</dd></div><div><dt>Specification version</dt><dd>{selected.specification_version}</dd></div><div><dt>Provenance checksum</dt><dd><code>{selected.provenance_checksum.slice(0, 12)}</code></dd></div></dl><h3>Retained specifications</h3><dl className="catalog-specification-list">{Object.entries(selected.specifications).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{typeof value === 'boolean' ? value ? 'Yes' : 'No' : String(value)}</dd></div>)}</dl><div className="inventory-documents"><h3>Product documentation</h3>{selected.documents.length === 0 ? <p className="empty-state">No STATIC product documentation was applicable when this asset was created.</p> : <ul>{selected.documents.map((item) => <li key={item.publication_id}><button type="button" onClick={() => { void openDocument(selected, item) }}><FileText size={16} /><span><strong>{item.title}</strong><small>{item.category} · retained {new Date(item.published_at).toLocaleDateString()}</small></span><CheckCircle2 size={15} aria-label="Signature verified" /></button></li>)}</ul>}</div>{document && <section className="retained-document"><div className="section-heading"><div><h3>{document.title}</h3><p>{document.reason}</p></div><button type="button" className="secondary-button" onClick={() => setDocument(null)}>Close</button></div><SanitizedMarkdown html={document.sanitized_html} />{document.artifacts.map((artifact) => <a className="secondary-button" key={artifact.id} href={client.artifactUrl(workspace, selected.id, document.publication_id, artifact.id)}>{artifact.kind === 'pdf' ? 'Download retained PDF' : `Download ${artifact.filename}`}</a>)}</section>}</> : <p className="empty-state">Choose an asset to inspect retained provenance.</p>}</section></div>}
    {creating && <section className="content-section inventory-create" aria-labelledby="new-asset-heading"><div className="section-heading"><div><h2 id="new-asset-heading">New asset from supplier model</h2><p>The current model revision, specifications, and applicable STATIC publications will be retained.</p></div></div><label className="inventory-model-search"><span>Find a supplier model</span><div><Search size={16} /><input autoFocus value={modelQuery} onChange={(event) => setModelQuery(event.target.value)} placeholder="Search supplier, product, model, or SKU" /></div></label><label><span>Supplier model</span><select value={modelId} onChange={(event) => setModelId(event.target.value)}><option value="">Choose a model…</option>{modelChoices.map((model) => <option key={model.id} value={model.id}>{model.supplier_name} · {model.product_name} · {model.name} ({model.model_number})</option>)}</select></label>{choice && <p className="inventory-choice-note">Revision {choice.revision} · {Object.keys(choice.specifications).length} retained specifications</p>}<label><span>Asset name (optional)</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder={choice?.name ?? 'Asset display name'} /></label><div className="form-actions"><button type="button" className="primary-button" disabled={saving || !modelId} onClick={() => { void createAsset() }}>{saving ? 'Creating…' : 'Create asset'}</button><button type="button" className="secondary-button" disabled={saving} onClick={() => setCreating(false)}>Cancel</button></div></section>}
    {phase === 'ready' && selected?.kind === 'hardware' && <section className="content-section inventory-lifecycle-panel"><HardwareLifecycle asset={selected} workspace={workspace} client={client} canManage={canManage} onChange={(hardware) => updateHardware(selected.id, hardware)} /></section>}
    {phase === 'ready' && selected?.kind === 'software' && <section className="content-section inventory-lifecycle-panel"><SoftwareInstallation asset={selected} workspace={workspace} client={client} canManage={canManage} onChange={(installation) => updateSoftware(selected.id, installation)} /></section>}
  </>
}
