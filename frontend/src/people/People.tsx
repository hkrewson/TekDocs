import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Pencil, Search, Settings2, Trash2 } from 'lucide-react'
import type { WorkspaceContext } from '../workspaces/api'
import { browserSitesClient } from '../sites/api'
import type { SiteRecord, SitesClient } from '../sites/api'
import { browserPeopleClient } from './api'
import type { PeopleClient, PeopleQuery, PersonFilterField, PersonInput, PersonRecord, PersonSortField } from './api'

type PersonColumn = PersonSortField

const columnLabels: Record<PersonColumn, string> = {
  full_name: 'Full name',
  preferred_name: 'Preferred name',
  kind: 'Relationship',
  role: 'Role',
  responsibility: 'Responsibility',
  location: 'Location',
  office: 'Office',
  phone: 'Phone',
  email: 'Email',
}
const optionalColumns = Object.keys(columnLabels).filter((column) => column !== 'full_name') as Exclude<PersonColumn, 'full_name'>[]
const defaultColumns: PersonColumn[] = ['full_name', 'preferred_name', 'role', 'location', 'office', 'phone', 'email']
const preferenceKey = 'tekdocs.people.visible-columns.v1'
const emptyInput: PersonInput = {
  full_name: '',
  preferred_name: '',
  kind: 'contact',
  role: '',
  responsibility: '',
  location: '',
  office: '',
  site_id: null,
  structured_location_id: null,
  phone: '',
  email: '',
}
const initialQuery: PeopleQuery = {
  q: '',
  filter_field: '',
  filter_value: '',
  ordering: 'full_name',
  page: 1,
  page_size: 25,
}

function storedColumns(): PersonColumn[] {
  try {
    const stored = JSON.parse(window.localStorage.getItem(preferenceKey) ?? 'null') as unknown
    if (!Array.isArray(stored)) return defaultColumns
    const valid = stored.filter((column): column is PersonColumn => typeof column === 'string' && column in columnLabels)
    return ['full_name', ...valid.filter((column) => column !== 'full_name')]
  } catch {
    return defaultColumns
  }
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

function PersonForm({ person, workspaceName, sites, sitesUnavailable, saving, onCancel, onSave }: {
  person: PersonRecord | null
  workspaceName: string
  sites: SiteRecord[]
  sitesUnavailable: boolean
  saving: boolean
  onCancel: () => void
  onSave: (input: PersonInput) => Promise<void>
}) {
  const [input, setInput] = useState<PersonInput>(() => person ? {
    full_name: person.full_name,
    preferred_name: person.preferred_name,
    kind: person.kind,
    role: person.role,
    responsibility: person.responsibility,
    location: person.location,
    office: person.office,
    site_id: person.site_id,
    structured_location_id: person.structured_location_id,
    phone: person.phone,
    email: person.email,
  } : emptyInput)
  const selectedSite = sites.find((site) => site.id === input.site_id)
  const selectedLocation = selectedSite?.locations.find((location) => location.id === input.structured_location_id)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    void onSave(input)
  }

  return (
    <section className="content-section people-form-section" aria-labelledby="people-form-heading">
      <div className="section-heading"><div><h2 id="people-form-heading">{person ? `Edit ${person.full_name}` : 'Add person'}</h2><p>This relationship belongs to {workspaceName}.</p></div></div>
      <form className="people-form" onSubmit={submit}>
        <label>Full name<input autoFocus required maxLength={240} value={input.full_name} onChange={(event) => setInput({ ...input, full_name: event.target.value })} /></label>
        <label>Preferred name <span>Optional</span><input maxLength={160} value={input.preferred_name} onChange={(event) => setInput({ ...input, preferred_name: event.target.value })} /></label>
        <label>Relationship<select value={input.kind} onChange={(event) => setInput({ ...input, kind: event.target.value as PersonInput['kind'] })}><option value="employee">Employee</option><option value="contact">Contact</option></select></label>
        <label>Role <span>Optional</span><input maxLength={160} value={input.role} onChange={(event) => setInput({ ...input, role: event.target.value })} /></label>
        <label className="people-form-wide">Responsibility <span>Optional</span><input maxLength={240} value={input.responsibility} onChange={(event) => setInput({ ...input, responsibility: event.target.value })} /></label>
        <label>Structured site <span>Optional workspace-owned site</span><select value={input.site_id ?? ''} disabled={sitesUnavailable} onChange={(event) => { const site = sites.find((item) => item.id === event.target.value); setInput({ ...input, site_id: site?.id ?? null, structured_location_id: null, location: site?.name ?? input.location }) }}><option value="">No structured site</option>{input.site_id && !selectedSite && <option value={input.site_id}>Archived or unavailable site</option>}{sites.map((site) => <option key={site.id} value={site.id}>{site.name}</option>)}</select></label>
        <label>Structured location <span>Optional office, room, or desk</span><select value={input.structured_location_id ?? ''} disabled={!selectedSite || sitesUnavailable} onChange={(event) => { const location = selectedSite?.locations.find((item) => item.id === event.target.value); setInput({ ...input, structured_location_id: location?.id ?? null, office: location?.name ?? input.office }) }}><option value="">No structured location</option>{input.structured_location_id && !selectedLocation && <option value={input.structured_location_id}>Archived or unavailable location</option>}{selectedSite?.locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label>
        <label>Location label <span>Retained fallback text</span><input maxLength={160} value={input.location} onChange={(event) => setInput({ ...input, location: event.target.value })} /></label>
        <label>Office label <span>Retained fallback text</span><input maxLength={120} value={input.office} onChange={(event) => setInput({ ...input, office: event.target.value })} /></label>
        <label>Phone <span>Optional</span><input type="tel" maxLength={64} value={input.phone} onChange={(event) => setInput({ ...input, phone: event.target.value })} /></label>
        <label>Email <span>Optional</span><input type="email" maxLength={254} value={input.email} onChange={(event) => setInput({ ...input, email: event.target.value })} /></label>
        <div className="form-actions"><button className="primary-button" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save person'}</button><button className="secondary-button" type="button" disabled={saving} onClick={onCancel}>Cancel</button></div>
      </form>
    </section>
  )
}

function cellValue(person: PersonRecord, column: PersonColumn) {
  if (column === 'kind') return person.kind === 'employee' ? 'Employee' : 'Contact'
  const value = person[column]
  if (!value) return '—'
  if (column === 'email') return <a href={`mailto:${value}`}>{value}</a>
  if (column === 'phone') return <a href={`tel:${value}`}>{value}</a>
  return value
}

export function People({ workspace, client = browserPeopleClient, sitesClient = browserSitesClient }: { workspace: WorkspaceContext | null; client?: PeopleClient; sitesClient?: SitesClient }) {
  const scope = useMemo(() => ({ organizationId: workspace?.id }), [workspace?.id])
  const scopeKey = workspace?.id ?? 'msp'
  const workspaceName = workspace?.name ?? 'the MSP'
  const [query, setQuery] = useState<PeopleQuery>(initialQuery)
  const [loaded, setLoaded] = useState<{ scopeKey: string; result: Awaited<ReturnType<PeopleClient['list']>> } | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [editing, setEditing] = useState<PersonRecord | 'new' | null>(null)
  const [archiving, setArchiving] = useState<PersonRecord | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [visibleColumns, setVisibleColumns] = useState<PersonColumn[]>(storedColumns)
  const [columnsOpen, setColumnsOpen] = useState(false)
  const [revision, setRevision] = useState(0)
  const [placementSites, setPlacementSites] = useState<{ scopeKey: string; sites: SiteRecord[] } | null>(null)
  const [sitesErrorScopeKey, setSitesErrorScopeKey] = useState<string | null>(null)
  const settingsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.list(scope, query, controller.signal)
        .then((result) => { if (!controller.signal.aborted) { setLoaded({ scopeKey, result }); setPhase('ready'); setError(null) } })
        .catch((loadError: unknown) => { if (!controller.signal.aborted) { setPhase('error'); setError(errorMessage(loadError, 'People could not be loaded.')) } })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, query, revision, scope, scopeKey])

  useEffect(() => {
    const controller = new AbortController()
    sitesClient.list(scope, '', controller.signal)
      .then((result) => { if (!controller.signal.aborted) { setPlacementSites({ scopeKey, sites: result.results }); setSitesErrorScopeKey(null) } })
      .catch(() => { if (!controller.signal.aborted) { setPlacementSites(null); setSitesErrorScopeKey(scopeKey) } })
    return () => controller.abort()
  }, [scope, scopeKey, sitesClient, revision])

  const result = loaded?.scopeKey === scopeKey ? loaded.result : null
  const visiblePhase = loaded && loaded.scopeKey !== scopeKey ? 'loading' : phase
  const sites = placementSites?.scopeKey === scopeKey ? placementSites.sites : []
  const sitesUnavailable = sitesErrorScopeKey === scopeKey

  useEffect(() => {
    if (!columnsOpen) return
    const close = (event: MouseEvent) => { if (!settingsRef.current?.contains(event.target as Node)) setColumnsOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [columnsOpen])

  const changeQuery = (changes: Partial<PeopleQuery>) => {
    setQuery((current) => ({ ...current, ...changes, page: changes.page ?? 1 }))
  }

  const toggleColumn = (column: Exclude<PersonColumn, 'full_name'>) => {
    setVisibleColumns((current) => {
      const next = current.includes(column) ? current.filter((item) => item !== column) : [...current, column]
      window.localStorage.setItem(preferenceKey, JSON.stringify(next))
      return next
    })
  }

  const sort = (column: PersonSortField) => {
    const next = query.ordering === column ? `-${column}` as const : column
    changeQuery({ ordering: next })
  }

  const save = async (input: PersonInput) => {
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      if (editing === 'new') await client.create(scope, input)
      else await client.update(scope, editing!.id, input)
      setEditing(null)
      setMessage(editing === 'new' ? 'Person added.' : 'Person updated.')
      setRevision((value) => value + 1)
    } catch (saveError) {
      setError(errorMessage(saveError, 'The person could not be saved.'))
    } finally {
      setSaving(false)
    }
  }

  const archive = async () => {
    if (!archiving) return
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      await client.archive(scope, archiving.id)
      setArchiving(null)
      setMessage('Person archived from this workspace.')
      setRevision((value) => value + 1)
    } catch (archiveError) {
      setError(errorMessage(archiveError, 'The person could not be archived.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <header className="page-header"><div><h1>People</h1><p>{workspace ? `Employees and contacts associated with ${workspace.name}.` : 'MSP employees and shared contacts.'}</p></div><button className="primary-button" type="button" onClick={() => { setEditing('new'); setArchiving(null); setMessage(null) }}>New person</button></header>
      {error && <div className="form-error people-error" role="alert">{error}</div>}
      {message && <div className="form-success" role="status">{message}</div>}
      {editing && <PersonForm key={editing === 'new' ? 'new' : editing.id} person={editing === 'new' ? null : editing} workspaceName={workspaceName} sites={sites} sitesUnavailable={sitesUnavailable} saving={saving} onCancel={() => setEditing(null)} onSave={save} />}
      <section className="content-section people-list-section" aria-labelledby="people-list-heading">
        <div className="section-heading people-list-heading"><h2 id="people-list-heading">Directory</h2><span>{result ? `${result.count} ${result.count === 1 ? 'person' : 'people'}` : 'Loading'}</span></div>
        <div className="people-toolbar">
          <label className="people-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search all person fields</span><input type="search" value={query.q} onChange={(event) => changeQuery({ q: event.target.value })} placeholder="Search people" /></label>
          <label>Filter field<select aria-label="Filter field" value={query.filter_field} onChange={(event) => changeQuery({ filter_field: event.target.value as PersonFilterField | '', filter_value: '' })}><option value="">No field filter</option>{optionalColumns.map((column) => <option key={column} value={column}>{columnLabels[column]}</option>)}</select></label>
          <label>Filter value<input aria-label="Filter value" value={query.filter_value} disabled={!query.filter_field} onChange={(event) => changeQuery({ filter_value: event.target.value })} placeholder={query.filter_field ? `Filter ${columnLabels[query.filter_field].toLowerCase()}` : 'Choose a field'} /></label>
          <div className="column-settings" ref={settingsRef}>
            <button className="secondary-button column-settings-trigger" type="button" aria-label="Choose visible columns" aria-expanded={columnsOpen} onClick={() => setColumnsOpen((open) => !open)}><Settings2 size={16} aria-hidden="true" /></button>
            {columnsOpen && <fieldset className="column-settings-popover"><legend>Visible columns</legend>{optionalColumns.map((column) => <label key={column}><input type="checkbox" checked={visibleColumns.includes(column)} onChange={() => toggleColumn(column)} />{columnLabels[column]}</label>)}</fieldset>}
          </div>
        </div>
        {visiblePhase === 'loading' && <p className="people-state" role="status">Loading people…</p>}
        {visiblePhase === 'error' && <p className="people-state">The directory is unavailable.</p>}
        {visiblePhase === 'ready' && result?.results.length === 0 && <p className="people-state">{query.q || query.filter_value ? 'No people match the current search and filter.' : 'No people have been added to this workspace.'}</p>}
        {visiblePhase === 'ready' && result && result.results.length > 0 && (
          <div className="people-table-wrap">
            <table className="people-table">
              <thead><tr>{visibleColumns.map((column) => <th key={column} scope="col" aria-sort={query.ordering === column ? 'ascending' : query.ordering === `-${column}` ? 'descending' : 'none'}><button type="button" onClick={() => sort(column)}>{columnLabels[column]}{query.ordering === column && <ArrowUp size={13} aria-hidden="true" />}{query.ordering === `-${column}` && <ArrowDown size={13} aria-hidden="true" />}</button></th>)}<th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>{result.results.map((person) => <tr key={person.association_id}>{visibleColumns.map((column) => <td key={column} data-label={columnLabels[column]}>{cellValue(person, column)}</td>)}<td className="people-row-actions"><button className="row-action" type="button" onClick={() => { setEditing(person); setArchiving(null); setMessage(null) }}><Pencil size={15} aria-hidden="true" />Edit <span className="sr-only">{person.full_name}</span></button><button className="row-action danger" type="button" onClick={() => { setArchiving(person); setEditing(null); setMessage(null) }}><Trash2 size={15} aria-hidden="true" />Archive <span className="sr-only">{person.full_name}</span></button></td></tr>)}</tbody>
            </table>
          </div>
        )}
        {visiblePhase === 'ready' && result && result.count > result.page_size && <nav className="people-pagination" aria-label="People pages"><button className="secondary-button" type="button" disabled={result.page === 1} onClick={() => changeQuery({ page: result.page - 1 })}><ChevronLeft size={15} />Previous</button><span>Page {result.page}</span><button className="secondary-button" type="button" disabled={!result.has_more} onClick={() => changeQuery({ page: result.page + 1 })}>Next<ChevronRight size={15} /></button></nav>}
        {archiving && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-person-heading"><div><strong id="archive-person-heading">Archive {archiving.full_name}?</strong><p>This removes the relationship from {workspaceName}. Other future associations to the same person identity are unaffected.</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? 'Archiving…' : 'Archive person'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setArchiving(null)}>Cancel</button></div></div>}
      </section>
    </>
  )
}
