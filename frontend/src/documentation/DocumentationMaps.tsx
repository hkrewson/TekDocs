import { Archive, ArrowDown, ArrowUp, Check, Download, FileArchive, GitBranch, IndentIncrease, Outdent, Plus, Save, X } from 'lucide-react'
import React, { useEffect, useMemo, useState } from 'react'
import type { WorkspaceContext } from '../workspaces/api'
import { documentationMapsClient, type DocumentationMap, type MapAudience, type MapChoices, type MapEntryInput, type MapEntryKind, type MapInput, type MapPreview, type MapType } from './mapsApi'

type DraftEntry = { key: string; depth: number; kind: MapEntryKind; target: string; label: string; url: string }
const mapTypes: { value: MapType; label: string }[] = [
  { value: 'operating_manual', label: 'Operating manual' }, { value: 'disaster_recovery', label: 'Disaster recovery' },
  { value: 'onboarding', label: 'Onboarding' }, { value: 'compliance', label: 'Compliance' },
  { value: 'handoff', label: 'Client handoff' }, { value: 'general', label: 'General' },
]

function message(error: unknown) { return error instanceof Error ? error.message : 'The documentation map request was not completed.' }

function entriesFrom(record: DocumentationMap): DraftEntry[] {
  const depths = new Map<string, number>()
  return record.current_revision.entries.map((entry) => {
    const depth = entry.parent_id ? (depths.get(entry.parent_id) ?? -1) + 1 : 0
    depths.set(entry.id, depth)
    return { key: entry.id, depth, kind: entry.kind, target: entry.document_id ?? entry.publication_id ?? entry.map_id ?? '', label: entry.label, url: entry.external_url }
  })
}

function blankInput(): MapInput { return { title: '', purpose: '', map_type: 'general', audience: 'msp_internal', owner_id: null, entries: [] } }

export function DocumentationMaps({ workspace, onShowDocuments }: { workspace: WorkspaceContext | null; onShowDocuments: () => void }) {
  const [records, setRecords] = useState<DocumentationMap[]>([])
  const [choices, setChoices] = useState<MapChoices>({ documents: [], publications: [], maps: [], owners: [] })
  const [selected, setSelected] = useState<DocumentationMap | 'new' | null>(null)
  const [input, setInput] = useState<MapInput>(blankInput())
  const [entries, setEntries] = useState<DraftEntry[]>([])
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [preview, setPreview] = useState<MapPreview | null>(null)
  const [formats, setFormats] = useState<string[]>([])

  async function load() {
    setPhase('loading'); setError(null)
    try {
      const [maps, available] = await Promise.all([documentationMapsClient.list(workspace), documentationMapsClient.choices(workspace)])
      setRecords(maps.results); setChoices(available); setPhase('ready')
    } catch (reason) { setError(message(reason)); setPhase('error') }
  }
  useEffect(() => {
    let active = true
    void Promise.all([documentationMapsClient.list(workspace), documentationMapsClient.choices(workspace)]).then(([maps, available]) => {
      if (!active) return
      setRecords(maps.results); setChoices(available); setPhase('ready')
    }).catch((reason: unknown) => {
      if (!active) return
      setError(message(reason)); setPhase('error')
    })
    return () => { active = false }
  }, [workspace])

  function open(record: DocumentationMap) {
    setSelected(record); setPreview(null); setNotice(null)
    setInput({ title: record.title, purpose: record.purpose, map_type: record.map_type, audience: record.audience, owner_id: record.owner_id, entries: [] })
    setEntries(entriesFrom(record))
  }
  function create() { setSelected('new'); setInput(blankInput()); setEntries([]); setPreview(null); setNotice(null) }

  const choiceGroups = useMemo(() => ({
    document: choices.documents,
    document_revision: choices.documents.filter((item) => item.current_revision_id),
    publication: choices.publications,
    map: choices.maps.filter((item) => item.id !== (selected === 'new' || selected === null ? '' : selected.id)),
    external: [],
  }), [choices, selected])

  function payloadEntries(): MapEntryInput[] {
    return entries.map((entry, index) => {
      let parent_index: number | null = null
      if (entry.depth > 0) {
        for (let candidate = index - 1; candidate >= 0; candidate -= 1) {
          if (entries[candidate].depth === entry.depth - 1) { parent_index = candidate; break }
        }
      }
      const base: MapEntryInput = { parent_index, position: entries.slice(0, index).filter((item, sibling) => {
        let siblingParent: number | null = null
        if (item.depth > 0) for (let candidate = sibling - 1; candidate >= 0; candidate -= 1) if (entries[candidate].depth === item.depth - 1) { siblingParent = candidate; break }
        return siblingParent === parent_index
      }).length, kind: entry.kind, label: entry.label }
      if (entry.kind === 'document') base.document_id = entry.target
      if (entry.kind === 'document_revision') { base.document_id = entry.target; base.document_revision_id = choices.documents.find((item) => item.id === entry.target)?.current_revision_id ?? null }
      if (entry.kind === 'publication') base.publication_id = entry.target
      if (entry.kind === 'map') base.map_id = entry.target
      if (entry.kind === 'external') base.external_url = entry.url
      return base
    })
  }

  async function save() {
    if (!input.title.trim()) { setError('Enter a map title.'); return }
    if (entries.some((entry) => entry.kind === 'external' ? !entry.url.trim() : !entry.target)) { setError('Choose a source for every map entry.'); return }
    setSaving(true); setError(null); setNotice(null)
    try {
      const body = { ...input, entries: payloadEntries() }
      const record = selected === 'new'
        ? await documentationMapsClient.create(workspace, body)
        : await documentationMapsClient.update(workspace, selected!.id, body, selected!.current_revision.id)
      await load(); open(record); setNotice(selected === 'new' ? 'Map created.' : 'New map revision saved.')
    } catch (reason) { setError(message(reason)) } finally { setSaving(false) }
  }

  async function inspect() {
    if (!selected || selected === 'new') return
    try { setPreview(await documentationMapsClient.preview(workspace, selected.id)) }
    catch (reason) { setError(message(reason)) }
  }

  async function review(state: 'approved' | 'changes_requested') {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try { const record = await documentationMapsClient.review(workspace, selected.id, state); setRecords((items) => items.map((item) => item.id === record.id ? record : item)); open(record); setNotice(state === 'approved' ? 'Map approved.' : 'Changes requested.') }
    catch (reason) { setError(message(reason)) } finally { setSaving(false) }
  }

  async function createBaseline() {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try { await documentationMapsClient.baseline(workspace, selected.id, selected.current_revision.id, formats); await load(); setSelected(null); setNotice('Retained baseline created.') }
    catch (reason) { setError(message(reason)) } finally { setSaving(false) }
  }

  async function archive() {
    if (!selected || selected === 'new' || !window.confirm(`Archive “${selected.title}”?`)) return
    setSaving(true)
    try { await documentationMapsClient.archive(workspace, selected.id); setSelected(null); await load(); setNotice('Map archived.') }
    catch (reason) { setError(message(reason)) } finally { setSaving(false) }
  }

  function move(index: number, direction: -1 | 1) { const target = index + direction; if (target < 0 || target >= entries.length) return; const next = [...entries]; [next[index], next[target]] = [next[target], next[index]]; if (target === 0) next[target].depth = 0; setEntries(next) }
  function updateEntry(index: number, patch: Partial<DraftEntry>) { setEntries((items) => items.map((item, current) => current === index ? { ...item, ...patch } : item)) }

  return <>
    <header className="page-header"><div><h1>Documentation maps</h1><p>Arrange live documents, exact revisions, publications, and subordinate maps into an operational runbook.</p><div className="segmented-control documentation-mode" aria-label="Documentation view"><button type="button" aria-pressed="false" onClick={onShowDocuments}>Documents</button><button type="button" aria-pressed="true">Maps</button></div></div><div className="page-actions"><button className="primary-button" type="button" onClick={create}><Plus size={16} />New map</button></div></header>
    {error && <div className="form-message error" role="alert">{error}</div>}{notice && <div className="form-message success" role="status">{notice}</div>}
    <section className="content-section map-index" aria-labelledby="map-index-heading"><div className="section-heading"><div><h2 id="map-index-heading">Maps</h2><p>Each save creates an append-only revision.</p></div><span>{records.length}</span></div>
      {phase === 'loading' && <p role="status">Loading maps…</p>}{phase === 'error' && <button className="secondary-button" onClick={() => void load()}>Try again</button>}
      {phase === 'ready' && records.length === 0 && <p className="empty-state">No maps have been created in this workspace.</p>}
      {records.length > 0 && <ul className="map-list">{records.map((record) => <li key={record.id}><button type="button" aria-current={selected !== 'new' && selected?.id === record.id ? 'true' : undefined} onClick={() => open(record)}><GitBranch size={17} /><span><strong>{record.title}</strong><small>{mapTypes.find((item) => item.value === record.map_type)?.label} · revision {record.current_revision.revision_number} · {record.review_state.replaceAll('_', ' ')}</small></span></button></li>)}</ul>}
    </section>
    {selected && <section className="content-section map-editor" aria-labelledby="map-editor-heading"><div className="section-heading"><div><h2 id="map-editor-heading">{selected === 'new' ? 'Create map' : selected.title}</h2><p>{selected === 'new' ? 'Build a reusable table of contents.' : `Revision ${selected.current_revision.revision_number} · ${selected.revision_count} retained revision${selected.revision_count === 1 ? '' : 's'}`}</p></div><button className="icon-button" type="button" aria-label="Close map editor" onClick={() => setSelected(null)}><X size={18} /></button></div>
      <div className="map-fields"><label>Title<input maxLength={240} value={input.title} onChange={(event) => setInput({ ...input, title: event.target.value })} /></label><label>Purpose<textarea maxLength={1000} value={input.purpose} onChange={(event) => setInput({ ...input, purpose: event.target.value })} /></label><label>Map type<select value={input.map_type} onChange={(event) => setInput({ ...input, map_type: event.target.value as MapType })}>{mapTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label>Audience<select value={input.audience} onChange={(event) => setInput({ ...input, audience: event.target.value as MapAudience })}><option value="msp_internal">MSP internal</option><option value="client_visible">Client visible</option></select></label><label>Owner<select value={input.owner_id ?? ''} onChange={(event) => setInput({ ...input, owner_id: event.target.value || null })}><option value="">No owner</option>{choices.owners.map((owner) => <option key={owner.id} value={owner.id}>{owner.title}</option>)}</select></label></div>
      <section className="map-entries" aria-labelledby="map-entries-heading"><div className="section-heading"><div><h3 id="map-entries-heading">Contents</h3><p>Indent an item to place it below the nearest item above it.</p></div><button className="secondary-button" type="button" onClick={() => setEntries((items) => [...items, { key: crypto.randomUUID(), depth: 0, kind: 'document', target: '', label: '', url: '' }])}><Plus size={15} />Add item</button></div>
        {entries.length === 0 && <p className="empty-state">Add the first item to begin the map.</p>}
        <ol>{entries.map((entry, index) => <li key={entry.key} style={{ '--map-depth': entry.depth } as React.CSSProperties}><span className="map-entry-number">{index + 1}</span><label><span>Source type</span><select value={entry.kind} onChange={(event) => updateEntry(index, { kind: event.target.value as MapEntryKind, target: '', url: '' })}><option value="document">Live document</option><option value="document_revision">Exact document revision</option><option value="publication">STATIC publication</option><option value="map">Subordinate map</option><option value="external">External link</option></select></label>{entry.kind === 'external' ? <label className="map-entry-source"><span>HTTPS URL</span><input type="url" placeholder="https://" value={entry.url} onChange={(event) => updateEntry(index, { url: event.target.value })} /></label> : <label className="map-entry-source"><span>Source</span><select value={entry.target} onChange={(event) => updateEntry(index, { target: event.target.value })}><option value="">Choose…</option>{choiceGroups[entry.kind].map((choice) => <option key={choice.id} value={choice.id}>{choice.title} · {choice.detail}</option>)}</select></label>}<label className="map-entry-label"><span>Display label (optional)</span><input value={entry.label} onChange={(event) => updateEntry(index, { label: event.target.value })} /></label><div className="map-entry-actions"><button type="button" aria-label="Move up" disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp size={15} /></button><button type="button" aria-label="Move down" disabled={index === entries.length - 1} onClick={() => move(index, 1)}><ArrowDown size={15} /></button><button type="button" aria-label="Indent" disabled={index === 0 || entry.depth >= entries[index - 1].depth + 1} onClick={() => updateEntry(index, { depth: entry.depth + 1 })}><IndentIncrease size={15} /></button><button type="button" aria-label="Outdent" disabled={entry.depth === 0} onClick={() => updateEntry(index, { depth: entry.depth - 1 })}><Outdent size={15} /></button><button type="button" aria-label="Remove" onClick={() => setEntries((items) => items.filter((_, current) => current !== index))}><X size={15} /></button></div></li>)}</ol>
      </section>
      <div className="form-actions"><button className="primary-button" type="button" disabled={saving} onClick={() => void save()}><Save size={15} />{saving ? 'Saving…' : selected === 'new' ? 'Create map' : 'Save new revision'}</button>{selected !== 'new' && <><button className="secondary-button" type="button" onClick={() => void inspect()}>Check &amp; preview</button><button className="secondary-button" type="button" disabled={saving} onClick={() => void review('approved')}><Check size={15} />Approve</button><button className="secondary-button" type="button" disabled={saving} onClick={() => void review('changes_requested')}>Request changes</button><button className="danger-button" type="button" disabled={saving} onClick={() => void archive()}><Archive size={15} />Archive</button></>}</div>
      {preview && <section className="map-preview" aria-labelledby="map-preview-heading"><div className="section-heading"><div><h3 id="map-preview-heading">Readiness check</h3><p>{preview.blocker_count} blockers · {preview.warning_count} warnings</p></div></div>{preview.findings.length === 0 ? <p className="form-message success">This map is ready to baseline.</p> : <ul>{preview.findings.map((finding, index) => <li key={`${finding.code}-${index}`}><strong>{finding.severity}</strong><span>{finding.detail}</span></li>)}</ul>}<fieldset><legend>Optional rendered files</legend><label><input type="checkbox" checked={formats.includes('pdf')} onChange={(event) => setFormats((items) => event.target.checked ? [...items, 'pdf'] : items.filter((item) => item !== 'pdf'))} />PDF</label><label><input type="checkbox" checked={formats.includes('docx')} onChange={(event) => setFormats((items) => event.target.checked ? [...items, 'docx'] : items.filter((item) => item !== 'docx'))} />DOCX</label></fieldset><button className="primary-button" type="button" disabled={saving || preview.blocker_count > 0} onClick={() => void createBaseline()}><FileArchive size={15} />Create retained baseline</button></section>}
      {selected !== 'new' && selected.baselines.length > 0 && <section className="map-baselines" aria-labelledby="map-baselines-heading"><h3 id="map-baselines-heading">Retained baselines</h3><ul>{selected.baselines.map((baseline) => <li key={baseline.id}><span><strong>Revision {baseline.revision_number}</strong><small>{new Date(baseline.created_at).toLocaleString()} · {Math.ceil(baseline.byte_size / 1024)} KB · {baseline.formats.join(', ') || 'Markdown and HTML'}</small></span><a className="secondary-button" href={documentationMapsClient.baselineUrl(workspace, selected.id, baseline.id)}><Download size={15} />Download</a></li>)}</ul></section>}
    </section>}
  </>
}
