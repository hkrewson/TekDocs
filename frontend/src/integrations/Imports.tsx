import { useEffect, useRef, useState } from 'react'
import { Download, Upload } from 'lucide-react'

import { formatDateTime, translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import {
  browserImportsClient,
  IMPORT_RECORD_TYPES,
  IMPORT_SOURCE_FORMATS,
  type ImportBatch,
  type ImportRecordType,
  type ImportRow,
  type ImportSourceFormat,
  type ImportsClient,
} from './importsApi'

const SOURCE_LABELS: Record<ImportSourceFormat, string> = {
  tekdocs_bundle: translate('imports.sourceTekdocsBundle'), tekdocs_csv: translate('imports.sourceTekdocsCsv'),
  itflow_csv: translate('imports.sourceItflowCsv'), itglue_csv: translate('imports.sourceItglueCsv'),
  hudu_csv: translate('imports.sourceHuduCsv'),
}

const RECORD_LABELS: Record<ImportRecordType, string> = {
  organizations: translate('imports.typeOrganizations'), people: translate('imports.typePeople'),
  sites: translate('imports.typeSites'), locations: translate('imports.typeLocations'),
  vendors: translate('imports.typeVendors'), products: translate('imports.typeProducts'),
  models: translate('imports.typeModels'), assets: translate('imports.typeAssets'),
  software_licenses: translate('imports.typeSoftwareLicenses'), networks: translate('imports.typeNetworks'),
  documents: translate('imports.typeDocuments'), document_metadata: translate('imports.typeDocumentMetadata'),
  credential_references: translate('imports.typeCredentialReferences'),
}

const STATE_LABELS: Record<ImportBatch['state'], string> = {
  preview_ready: translate('imports.statePreviewReady'), applying: translate('imports.stateApplying'),
  applied: translate('imports.stateApplied'), cancelled: translate('imports.stateCancelled'),
  failed: translate('imports.stateFailed'),
}

const ACTION_LABELS = {
  create: translate('imports.actionCreate'), update: translate('imports.actionUpdate'),
  unchanged: translate('imports.actionUnchanged'), conflict: translate('imports.actionConflict'),
  rejected: translate('imports.actionRejected'),
} as const

function resultSummary(batch: ImportBatch) {
  return (Object.keys(ACTION_LABELS) as (keyof typeof ACTION_LABELS)[])
    .filter((action) => Boolean(batch.result_counts[action]))
    .map((action) => `${batch.result_counts[action]} ${ACTION_LABELS[action].toLowerCase()}`)
    .join(', ') || '—'
}

export function Imports({ workspace, client = browserImportsClient }: { workspace: WorkspaceContext; client?: ImportsClient }) {
  const availableRecordTypes = IMPORT_RECORD_TYPES.filter((value) => {
    if (workspace.kind === 'msp') return !['products', 'models', 'assets', 'software_licenses'].includes(value)
    if (['organizations', 'vendors'].includes(value)) return false
    if (['products', 'models'].includes(value)) return workspace.classifications.some((kind) => kind === 'vendor' || kind === 'manufacturer')
    if (['assets', 'software_licenses'].includes(value)) return workspace.classifications.includes('client')
    return true
  })
  const [batches, setBatches] = useState<ImportBatch[]>([])
  const [selected, setSelected] = useState<ImportBatch | null>(null)
  const [rows, setRows] = useState<ImportRow[]>([])
  const [sourceFormat, setSourceFormat] = useState<ImportSourceFormat>('tekdocs_csv')
  const [recordType, setRecordType] = useState<ImportRecordType>('sites')
  const [templateType, setTemplateType] = useState<ImportRecordType>('sites')
  const [file, setFile] = useState<File | null>(null)
  const [matches, setMatches] = useState<Record<string, string>>({})
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const controller = new AbortController()
    client.list(workspace, controller.signal).then((page) => {
      setBatches(page.results)
      setPhase('ready')
    }).catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client, workspace])

  useEffect(() => {
    if (!selected) return
    const controller = new AbortController()
    client.rows(workspace, selected, controller.signal).then((page) => setRows(page.results)).catch(() => {
      if (!controller.signal.aborted) setError(translate('imports.rowsFailed'))
    })
    return () => controller.abort()
  }, [client, selected, workspace])

  function replaceBatch(next: ImportBatch) {
    setBatches((current) => [next, ...current.filter((batch) => batch.id !== next.id)])
    setSelected(next)
  }

  async function preview() {
    if (!file) return
    setSaving(true); setError(null)
    try {
      const next = await client.preview(workspace, file, sourceFormat, recordType)
      replaceBatch(next); setFile(null); setMatches({})
      if (fileInput.current) fileInput.current.value = ''
    } catch (caught) { setError(caught instanceof Error ? caught.message : translate('imports.previewFailed')) }
    finally { setSaving(false) }
  }

  async function applyImport() {
    if (!selected) return
    setSaving(true); setError(null)
    try { replaceBatch(await client.apply(workspace, selected, matches)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : translate('imports.applyFailed')) }
    finally { setSaving(false) }
  }

  async function cancelImport() {
    if (!selected) return
    setSaving(true); setError(null)
    try { replaceBatch(await client.cancel(workspace, selected)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : translate('imports.cancelFailed')) }
    finally { setSaving(false) }
  }

  const pending = selected?.state === 'preview_ready'
  const blockingRows = rows.filter((row) => row.action === 'rejected' || (row.action === 'conflict' && !matches[row.id]))

  return <>
    <section className="content-section import-start" aria-labelledby="import-start-title">
      <div className="section-heading"><div><h2 id="import-start-title">{translate('imports.startTitle')}</h2><p>{translate('imports.startHelp')}</p></div></div>
      <div className="import-notice"><strong>{translate('imports.previewNoWrites')}</strong><span>{translate('imports.safetyHelp')}</span></div>
      <div className="form-grid import-upload-form">
        <label><span>{translate('imports.source')}</span><select value={sourceFormat} onChange={(event) => setSourceFormat(event.target.value as ImportSourceFormat)}>{IMPORT_SOURCE_FORMATS.map((value) => <option key={value} value={value}>{SOURCE_LABELS[value]}</option>)}</select></label>
        {sourceFormat !== 'tekdocs_bundle' && <label><span>{translate('imports.recordType')}</span><select value={recordType} onChange={(event) => setRecordType(event.target.value as ImportRecordType)}>{availableRecordTypes.map((value) => <option key={value} value={value}>{RECORD_LABELS[value]}</option>)}</select></label>}
        <label className="wide-field"><span>{translate('imports.file')}</span><input ref={fileInput} type="file" accept={sourceFormat === 'tekdocs_bundle' ? '.zip,application/zip' : '.csv,text/csv'} onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label>
        <div className="form-actions wide-field"><button className="primary-button" type="button" disabled={!file || saving} onClick={() => { void preview() }}><Upload size={15} />{saving ? translate('imports.processing') : translate('imports.preview')}</button></div>
      </div>
      <div className="import-template-row"><label><span>{translate('imports.template')}</span><select value={templateType} onChange={(event) => setTemplateType(event.target.value as ImportRecordType)}>{availableRecordTypes.map((value) => <option key={value} value={value}>{RECORD_LABELS[value]}</option>)}</select></label><a className="secondary-button" href={client.templateUrl(workspace, templateType)}><Download size={14} />{translate('imports.downloadTemplate')}</a></div>
    </section>
    {error && <div className="form-message error" role="alert">{error}</div>}
    <section className="content-section" aria-labelledby="import-history-title" aria-busy={phase === 'loading'}>
      <div className="section-heading"><div><h2 id="import-history-title">{translate('imports.historyTitle')}</h2><p>{translate('imports.historyHelp')}</p></div></div>
      {phase === 'loading' && <p className="empty-state" role="status">{translate('imports.loading')}</p>}
      {phase === 'error' && <p className="empty-state" role="alert">{translate('imports.loadFailed')}</p>}
      {phase === 'ready' && batches.length === 0 && <p className="empty-state">{translate('imports.empty')}</p>}
      {phase === 'ready' && batches.length > 0 && <div className="table-scroll" role="group" aria-label={translate('imports.historyTable')} tabIndex={0}><table><thead><tr><th>{translate('imports.file')}</th><th>{translate('imports.source')}</th><th>{translate('imports.created')}</th><th>{translate('imports.state')}</th><th>{translate('imports.summary')}</th><th>{translate('imports.action')}</th></tr></thead><tbody>{batches.map((batch) => <tr key={batch.id} className={selected?.id === batch.id ? 'selected-row' : undefined}><td>{batch.source_filename}</td><td>{SOURCE_LABELS[batch.source_format]}</td><td>{formatDateTime(batch.created_at)}</td><td>{STATE_LABELS[batch.state]}</td><td>{resultSummary(batch)}</td><td><button className="secondary-button" type="button" onClick={() => { setSelected(batch); setMatches({}) }}>{translate('imports.review')}</button></td></tr>)}</tbody></table></div>}
    </section>
    {selected && <section className="content-section" aria-labelledby="import-preview-title">
      <div className="section-heading"><div><h2 id="import-preview-title">{translate('imports.previewTitle')}</h2><p>{selected.source_filename} · {translate('imports.expires', { date: formatDateTime(selected.expires_at) })}</p></div><div className="table-actions"><a className="secondary-button" href={client.reportUrl(workspace, selected)}><Download size={14} />{translate('imports.report')}</a>{pending && <button className="secondary-button" type="button" disabled={saving} onClick={() => { void cancelImport() }}>{translate('common.cancel')}</button>}<button className="primary-button" type="button" disabled={!pending || saving || blockingRows.length > 0} onClick={() => { void applyImport() }}>{saving ? translate('imports.processing') : translate('imports.apply')}</button></div></div>
      {blockingRows.length > 0 && <div className="form-message warning" role="status">{translate('imports.blocked', { count: blockingRows.length })}</div>}
      <div className="table-scroll" role="group" aria-label={translate('imports.previewTable')} tabIndex={0}><table><thead><tr><th>{translate('imports.row')}</th><th>{translate('imports.recordType')}</th><th>{translate('imports.externalKey')}</th><th>{translate('imports.action')}</th><th>{translate('imports.reason')}</th><th>{translate('imports.decision')}</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{row.row_number}</td><td>{RECORD_LABELS[row.record_type]}</td><td><code>{row.external_key}</code></td><td>{ACTION_LABELS[row.action]}</td><td><code>{row.reason_code || '—'}</code></td><td>{pending && row.action === 'conflict' && row.local_entity_id ? <label className="inline-choice"><input type="checkbox" checked={Boolean(matches[row.id])} onChange={(event) => setMatches((current) => { const next = { ...current }; if (event.target.checked && row.local_entity_id) next[row.id] = row.local_entity_id; else delete next[row.id]; return next })} /><span>{translate('imports.useExisting')}</span></label> : '—'}</td></tr>)}</tbody></table></div>
    </section>}
  </>
}
