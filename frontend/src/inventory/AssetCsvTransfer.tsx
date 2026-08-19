import { useState } from 'react'
import { Download, Upload, X } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { AssetCsvPreview, InventoryClient } from './api'
import type { WorkspaceContext } from '../workspaces/api'

export function AssetCsvTransfer({ workspace, client, canManage, onApplied }: {
  workspace: WorkspaceContext
  client: InventoryClient
  canManage: boolean
  onApplied: () => void
}) {
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<AssetCsvPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<string | null>(null)

  function close() {
    if (busy) return
    setOpen(false); setFile(null); setPreview(null); setError(null); setResult(null)
  }

  async function previewFile() {
    if (!file) return
    setBusy(true); setError(null); setResult(null)
    try { setPreview(await client.previewAssetCsv(workspace, file)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'The CSV could not be previewed.') }
    finally { setBusy(false) }
  }

  async function applyFile() {
    if (!file || !preview?.preview_token) return
    setBusy(true); setError(null)
    try {
      const applied = await client.applyAssetCsv(workspace, file, preview.preview_token)
      setResult(`${applied.created} created, ${applied.updated} updated, ${applied.skipped} unchanged.`)
      setPreview(null); setFile(null); onApplied()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The CSV import could not be applied.') }
    finally { setBusy(false) }
  }

  return <>
    <div className="asset-transfer-actions">
      <a className="secondary-button" href={client.assetCsvExportUrl(workspace)} download><Download size={15} />Export CSV</a>
      {canManage && <button className="secondary-button" type="button" onClick={() => setOpen(true)}><Upload size={15} />{translate('inventory.importCsv')}</button>}
    </div>
    {open && <section className="content-section asset-csv-panel" aria-labelledby="asset-csv-heading">
      <div className="section-heading"><div><h2 id="asset-csv-heading">Import assets from CSV</h2><p>Preview is required. Applying a valid file is atomic and safe to retry.</p></div><button className="icon-button" type="button" aria-label="Close CSV import" disabled={busy} onClick={close}><X size={16} /></button></div>
      <p className="asset-csv-guidance">Start with the canonical template and set each row's <code>schema_version</code> to <code>tekdocs.assets.v1</code>. New rows need a stable <code>import_key</code>; exported rows use their existing <code>asset_id</code>. Assignments, costs, licenses, contracts, attachments, credentials, and disposal are intentionally excluded.</p>
      <a className="secondary-button" href={client.assetCsvTemplateUrl(workspace)} download><Download size={15} />Download template</a>
      <label className="asset-csv-file"><span>TekDocs asset CSV</span><input type="file" accept=".csv,text/csv" disabled={busy} onChange={(event) => { setFile(event.target.files?.[0] ?? null); setPreview(null); setResult(null); setError(null) }} /></label>
      {error && <div className="form-message error" role="alert">{error}</div>}
      {result && <div className="form-message success" role="status">{result}</div>}
      {file && !preview && <button className="primary-button" type="button" disabled={busy} onClick={() => { void previewFile() }}>{busy ? 'Validating…' : 'Preview changes'}</button>}
      {preview && <div className="asset-csv-preview">
        <dl><div><dt>Create</dt><dd>{preview.summary.create}</dd></div><div><dt>Update</dt><dd>{preview.summary.update}</dd></div><div><dt>Unchanged</dt><dd>{preview.summary.skip}</dd></div><div><dt>Errors</dt><dd>{preview.summary.errors}</dd></div></dl>
        {preview.errors.length > 0 && <ul className="asset-csv-errors" aria-label="CSV validation errors">{preview.errors.map((item) => <li key={`${item.row}-${item.message}`}><strong>Row {item.row}</strong><span>{item.message}</span></li>)}</ul>}
        {preview.rows.length > 0 && <div className="asset-csv-table-wrap"><table><thead><tr><th>Row</th><th>Asset</th><th>Type</th><th>Action</th><th>Fields</th></tr></thead><tbody>{preview.rows.map((item) => <tr key={item.row}><td>{item.row}</td><td>{item.name}</td><td>{item.kind}</td><td>{item.action}</td><td>{item.changes.join(', ') || '—'}</td></tr>)}</tbody></table></div>}
        <div className="form-actions"><button className="primary-button" type="button" disabled={busy || !preview.preview_token} onClick={() => { void applyFile() }}>{busy ? 'Importing…' : 'Apply import'}</button><button className="secondary-button" type="button" disabled={busy} onClick={() => { setPreview(null); setFile(null) }}>{translate('inventory.chooseAnotherFile')}</button></div>
      </div>}
    </section>}
  </>
}
