import { useEffect, useMemo, useState } from 'react'
import { History, Plus, TriangleAlert, X } from 'lucide-react'
import { translate } from '../i18n/localization'
import { CollectionPagination } from '../CollectionPagination'
import { browserDataFlowClient } from './dataFlowApi'
import type { FormEvent } from 'react'
import type { DataFlow, DataFlowChoice, DataFlowChoices, DataFlowClient, DataFlowDraft, DataFlowRevision } from './dataFlowApi'
import type { WorkspaceContext } from '../workspaces/api'

type Mode = 'read' | 'create' | 'edit'

const emptyChoices: DataFlowChoices = {
  endpoint_kinds: [], directions: [], transfer_mechanisms: [],
  data_classifications: [], protections: [], provenance_states: [],
}

const blank: DataFlowDraft = {
  name: '', source_kind: 'external', source_label: '', source_entity_id: null,
  destination_kind: 'external', destination_label: '', destination_entity_id: null,
  direction: 'one_way', transfer_mechanism: 'api', data_classification: 'internal',
  purpose: '', crosses_trust_boundary: false, protection: 'unknown',
  owner_entity_id: null, review_due_on: null, provenance: 'unverified_draft',
}

function draftFrom(revision: DataFlowRevision, name: string): DataFlowDraft {
  return {
    name,
    source_kind: revision.source_kind,
    source_entity_id: revision.source_entity_id,
    source_label: revision.source_label,
    destination_kind: revision.destination_kind,
    destination_entity_id: revision.destination_entity_id,
    destination_label: revision.destination_label,
    direction: revision.direction,
    transfer_mechanism: revision.transfer_mechanism,
    data_classification: revision.data_classification,
    purpose: revision.purpose,
    crosses_trust_boundary: revision.crosses_trust_boundary,
    protection: revision.protection,
    owner_entity_id: revision.owner_entity_id,
    review_due_on: revision.review_due_on,
    provenance: revision.provenance,
  }
}

function labelFor(options: DataFlowChoice[], value: string) {
  return options.find((option) => option.value === value)?.label ?? value
}

/** Provenance must never be readable as colour alone.
 *
 * ADR 0088 exists because a plausible diagram gets mistaken for evidence. A draft
 * therefore carries a warning icon and the words "not evidence" alongside its label,
 * so the distinction survives greyscale, forced colours, and a screen reader. */
function Provenance({ state, options }: { state: string; options: DataFlowChoice[] }) {
  const draft = state === 'unverified_draft'
  const label = labelFor(options, state)
  const text = draft ? `${label} · ${translate('dataFlows.notEvidence')}` : label
  return (
    <span className={`data-flow-provenance ${state}`}>
      {draft && <TriangleAlert size={12} aria-hidden="true" />}
      {text}
    </span>
  )
}

export function DataFlows({ workspace, client = browserDataFlowClient }: { workspace: WorkspaceContext | null; client?: DataFlowClient }) {
  const [records, setRecords] = useState<DataFlow[]>([])
  const [choices, setChoices] = useState<DataFlowChoices>(emptyChoices)
  const [canManage, setCanManage] = useState(false)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error' | 'unavailable'>('loading')
  const [mode, setMode] = useState<Mode>('read')
  const [form, setForm] = useState<DataFlowDraft>(blank)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [history, setHistory] = useState<DataFlowRevision[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageState, setPageState] = useState({ pageSize: 50, count: 0, hasMore: false })

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([client.list(workspace, page, controller.signal), client.choices(workspace, controller.signal)])
      .then(([result, vocabulary]) => {
        setRecords(result.results)
        setCanManage(result.can_manage)
        setPageState({ pageSize: result.page_size, count: result.count, hasMore: result.has_more })
        setChoices(vocabulary)
        setPhase('ready')
      })
      // Data flows carry their own permission, so a member who may read compliance can
      // still be refused here. That is not a page failure; the section simply does not
      // apply to them.
      .catch(() => { if (!controller.signal.aborted) setPhase('unavailable') })
    return () => controller.abort()
  }, [client, page, workspace])

  const selected = useMemo(() => records.find((record) => record.id === selectedId) ?? null, [records, selectedId])

  async function reload() {
    const result = await client.list(workspace, page)
    setRecords(result.results)
    setCanManage(result.can_manage)
    setPageState({ pageSize: result.page_size, count: result.count, hasMore: result.has_more })
  }

  async function perform(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      await reload()
      setMode('read')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The data flow could not be changed.')
    } finally {
      setBusy(false)
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    void perform(() => (mode === 'edit' && selected ? client.revise(workspace, selected.id, form) : client.create(workspace, form)))
  }

  async function openHistory(record: DataFlow) {
    setSelectedId(record.id)
    setHistory(null)
    setError(null)
    try {
      setHistory((await client.revisions(workspace, record.id)).results)
    } catch {
      setError('The revision history could not be loaded.')
    }
  }

  if (phase === 'unavailable') return null

  return (
    <section className="content-section compliance-data-flows" aria-labelledby="compliance-data-flows-heading">
      <div className="section-heading">
        <div>
          <h2 id="compliance-data-flows-heading">{translate('dataFlows.heading')}</h2>
          <p>{translate('dataFlows.intro')}</p>
        </div>
        {canManage && mode === 'read' && (
          <button
            type="button"
            className="primary-button"
            aria-label={translate('dataFlows.declare')}
            title={translate('dataFlows.declare')}
            onClick={() => { setForm(blank); setMode('create'); setError(null) }}
          >
            <Plus size={16} aria-hidden="true" />
            <span className="button-label">{translate('dataFlows.declare')}</span>
          </button>
        )}
      </div>

      {error && <div className="form-message error" role="alert">{error}</div>}
      {phase === 'loading' && <p className="empty-state" role="status">{translate('dataFlows.loading')}</p>}
      {phase === 'error' && <p className="empty-state" role="alert">{translate('dataFlows.unavailable')}</p>}

      {phase === 'ready' && mode !== 'read' && (
        <form className="data-flow-form" onSubmit={submit}>
          <label className="wide-field"><span>Name</span><input required maxLength={240} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
          <label className="wide-field"><span>Purpose</span><input required maxLength={1000} value={form.purpose} onChange={(event) => setForm({ ...form, purpose: event.target.value })} /></label>
          <label><span>Source</span><input required maxLength={240} value={form.source_label ?? ''} onChange={(event) => setForm({ ...form, source_kind: 'external', source_entity_id: null, source_label: event.target.value })} /></label>
          <label><span>Destination</span><input required maxLength={240} value={form.destination_label ?? ''} onChange={(event) => setForm({ ...form, destination_kind: 'external', destination_entity_id: null, destination_label: event.target.value })} /></label>
          <Choice label="Direction" value={form.direction} options={choices.directions} onChange={(value) => setForm({ ...form, direction: value })} />
          <Choice label="Transfer mechanism" value={form.transfer_mechanism} options={choices.transfer_mechanisms} onChange={(value) => setForm({ ...form, transfer_mechanism: value })} />
          <Choice label="Data classification" value={form.data_classification} options={choices.data_classifications} onChange={(value) => setForm({ ...form, data_classification: value })} />
          <Choice label="Protection" value={form.protection} options={choices.protections} onChange={(value) => setForm({ ...form, protection: value })} />
          <Choice label="Provenance" value={form.provenance} options={choices.provenance_states} onChange={(value) => setForm({ ...form, provenance: value })} />
          <label><span>Review due</span><input type="date" value={form.review_due_on ?? ''} onChange={(event) => setForm({ ...form, review_due_on: event.target.value || null })} /></label>
          <label className="checkbox-field"><input type="checkbox" checked={form.crosses_trust_boundary} onChange={(event) => setForm({ ...form, crosses_trust_boundary: event.target.checked })} /><span>Crosses a trust boundary</span></label>
          <div className="form-actions">
            <button type="submit" className="primary-button" disabled={busy}>{busy ? translate('dataFlows.saving') : mode === 'edit' ? translate('dataFlows.saveRevision') : translate('dataFlows.saveFlow')}</button>
            <button type="button" className="secondary-button" onClick={() => { setMode('read'); setError(null) }}>{translate('common.cancel')}</button>
          </div>
        </form>
      )}

      {phase === 'ready' && mode === 'read' && (records.length === 0 ? (
        <p className="empty-state">{translate('dataFlows.empty')}</p>
      ) : (
        <>
          <div className="network-table-wrap" role="group" aria-label={translate('dataFlows.table')} tabIndex={0}>
            <table className="network-table">
              <thead><tr><th>Flow</th><th>Moves between</th><th>Classification</th><th>Provenance</th><th>Revision</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {records.map((record) => {
                  const revision = record.current_revision
                  return (
                    <tr key={record.id} className={selectedId === record.id ? 'selected' : ''}>
                      <td><strong>{record.name}</strong><small>{revision?.purpose}</small></td>
                      <td>{revision ? `${revision.source_display_name} → ${revision.destination_display_name}` : ''}<small>{revision?.crosses_trust_boundary ? translate('dataFlows.crossesBoundary') : ''}</small></td>
                      <td>{revision ? labelFor(choices.data_classifications, revision.data_classification) : ''}<small>{revision ? labelFor(choices.protections, revision.protection) : ''}</small></td>
                      <td>{revision && <Provenance state={revision.provenance} options={choices.provenance_states} />}</td>
                      <td>{record.revision_count}</td>
                      <td>
                        <div className="table-actions">
                          <button type="button" className="secondary-button" onClick={() => { void openHistory(record) }}><History size={14} aria-hidden="true" />{translate('dataFlows.history')}</button>
                          {canManage && revision && <button type="button" className="secondary-button" onClick={() => { setSelectedId(record.id); setForm(draftFrom(revision, record.name)); setMode('edit'); setError(null) }}>{translate('common.edit')}</button>}
                          {canManage && <button type="button" className="secondary-button danger-button" disabled={busy} onClick={() => { void perform(() => client.archive(workspace, record.id)) }}>{translate('common.archive')}</button>}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <CollectionPagination label="Data flows" page={page} pageSize={pageState.pageSize} count={pageState.count} hasMore={pageState.hasMore} onPageChange={(next) => { setSelectedId(null); setHistory(null); setPage(next) }} />
        </>
      ))}

      {history && selected && (
        <div className="data-flow-history">
          <div className="section-heading">
            <div><h3>{translate('dataFlows.historyHeading', { name: selected.name })}</h3></div>
            <button className="icon-button" type="button" aria-label={translate('dataFlows.closeHistory')} onClick={() => setHistory(null)}><X size={16} /></button>
          </div>
          <div className="network-table-wrap" role="group" aria-label={translate('dataFlows.revisionTable')} tabIndex={0}>
            <table className="network-table">
              <thead><tr><th>Revision</th><th>Moves between</th><th>Classification</th><th>Protection</th><th>Provenance</th></tr></thead>
              <tbody>
                {history.map((revision) => (
                  <tr key={revision.id}>
                    <td><strong>{revision.revision_number}</strong></td>
                    <td>{revision.source_display_name} → {revision.destination_display_name}</td>
                    <td>{labelFor(choices.data_classifications, revision.data_classification)}</td>
                    <td>{labelFor(choices.protections, revision.protection)}</td>
                    <td><Provenance state={revision.provenance} options={choices.provenance_states} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  )
}

function Choice({ label, value, options, onChange }: { label: string; value: string; options: DataFlowChoice[]; onChange: (value: string) => void }) {
  return (
    <label>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  )
}
