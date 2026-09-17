import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Pencil, Plus, Search, Settings2, Trash2 } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { QuickDrawer } from '../collections/QuickDrawer'
import '../collections/collections.css'
import { translate } from '../i18n/localization'
import { FilterMenu } from '../FilterMenu'
import type { WorkspaceContext } from '../workspaces/api'
import { browserSitesClient } from '../sites/api'
import type { SiteRecord, SitesClient } from '../sites/api'
import { browserPeopleClient } from './api'
import type { PeopleClient, PeopleQuery, PersonFilterField, PersonInput, PersonRecord, PersonSortField } from './api'

type PersonColumn = PersonSortField

const columnLabels: Record<PersonColumn, string> = {
  full_name: translate('people.fullName'),
  preferred_name: translate('people.preferredName'),
  kind: translate('people.relationship'),
  role: translate('people.role'),
  responsibility: translate('people.responsibility'),
  location: translate('people.site'),
  office: translate('people.location'),
  phone: translate('people.phone'),
  email: translate('people.email'),
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
const placementSiteQuery = { q: '', ordering: 'name' as const, page: 1, page_size: 100 }

function personInput(person: PersonRecord | null): PersonInput {
  return person ? {
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
  } : emptyInput
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

function PersonForm({ person, workspaceName, sites, sitesUnavailable, saving, onCancel, onDirtyChange, onSave }: {
  person: PersonRecord | null
  workspaceName: string
  sites: SiteRecord[]
  sitesUnavailable: boolean
  saving: boolean
  onCancel: () => void
  onDirtyChange: (dirty: boolean) => void
  onSave: (input: PersonInput) => Promise<void>
}) {
  const initial = useMemo(() => personInput(person), [person])
  const [input, setInput] = useState<PersonInput>(initial)
  const selectedSite = sites.find((site) => site.id === input.site_id)
  const selectedLocation = selectedSite?.locations.find((location) => location.id === input.structured_location_id)

  useEffect(() => {
    onDirtyChange(JSON.stringify(input) !== JSON.stringify(initial))
    return () => onDirtyChange(false)
  }, [initial, input, onDirtyChange])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    void onSave(input)
  }

  return (
      <form className="record-form record-form-grid people-form operational-record-form" onSubmit={submit}>
        <p className="operational-record-context">{translate('people.workspaceHelp', { workspace: workspaceName })}</p>
        <label>{translate('people.fullName')}<input autoFocus required maxLength={240} value={input.full_name} onChange={(event) => setInput({ ...input, full_name: event.target.value })} /></label>
        <label>{translate('people.preferredName')} <span>{translate('common.optional')}</span><input maxLength={160} value={input.preferred_name} onChange={(event) => setInput({ ...input, preferred_name: event.target.value })} /></label>
        <label>{translate('people.relationship')}<select value={input.kind} onChange={(event) => setInput({ ...input, kind: event.target.value as PersonInput['kind'] })}><option value="employee">{translate('people.employee')}</option><option value="contact">{translate('people.contact')}</option></select></label>
        <label>{translate('people.role')} <span>{translate('common.optional')}</span><input maxLength={160} value={input.role} onChange={(event) => setInput({ ...input, role: event.target.value })} /></label>
        <label className="people-form-wide">{translate('people.responsibility')} <span>{translate('common.optional')}</span><input maxLength={240} value={input.responsibility} onChange={(event) => setInput({ ...input, responsibility: event.target.value })} /></label>
        <label>{translate('people.savedSite')} <span>{translate('common.optional')}</span><select value={input.site_id ?? ''} disabled={sitesUnavailable} onChange={(event) => { const site = sites.find((item) => item.id === event.target.value); setInput({ ...input, site_id: site?.id ?? null, structured_location_id: null, location: site?.name ?? input.location }) }}><option value="">{translate('people.noSavedSite')}</option>{input.site_id && !selectedSite && <option value={input.site_id}>{translate('people.unavailableSite')}</option>}{sites.map((site) => <option key={site.id} value={site.id}>{site.name}</option>)}</select></label>
        <label>{translate('people.savedLocation')} <span>{translate('common.optional')}</span><select value={input.structured_location_id ?? ''} disabled={!selectedSite || sitesUnavailable} onChange={(event) => { const location = selectedSite?.locations.find((item) => item.id === event.target.value); setInput({ ...input, structured_location_id: location?.id ?? null, office: location?.name ?? input.office }) }}><option value="">{translate('people.noSavedLocation')}</option>{input.structured_location_id && !selectedLocation && <option value={input.structured_location_id}>{translate('people.unavailableLocation')}</option>}{selectedSite?.locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label>
        {sitesUnavailable && <p className="field-guidance people-form-wide" role="status">{translate('people.sitesUnavailable')}</p>}
        <label>{translate('people.siteLabel')} <span>{translate('people.siteLabelHelp')}</span><input maxLength={160} value={input.location} onChange={(event) => setInput({ ...input, location: event.target.value })} /></label>
        <label>{translate('people.locationLabel')} <span>{translate('people.locationLabelHelp')}</span><input maxLength={120} value={input.office} onChange={(event) => setInput({ ...input, office: event.target.value })} /></label>
        <label>{translate('people.phone')} <span>{translate('common.optional')}</span><input type="tel" maxLength={64} value={input.phone} onChange={(event) => setInput({ ...input, phone: event.target.value })} /></label>
        <label>{translate('people.email')} <span>{translate('common.optional')}</span><input type="email" maxLength={254} value={input.email} onChange={(event) => setInput({ ...input, email: event.target.value })} /></label>
        <div className="form-actions"><button className="primary-button" type="submit" disabled={saving}>{saving ? translate('common.saving') : translate('people.save')}</button><button className="secondary-button" type="button" disabled={saving} onClick={onCancel}>{translate('common.cancel')}</button></div>
      </form>
  )
}

function PersonOverview({ person, onArchive, onEdit }: { person: PersonRecord; onArchive: () => void; onEdit: () => void }) {
  return <div className="operational-record">
    <div className="operational-record-actions"><button className="primary-button" type="button" onClick={onEdit}><Pencil size={15} aria-hidden="true" />{translate('people.editDetails')}</button><button className="secondary-button danger" type="button" onClick={onArchive}><Trash2 size={15} aria-hidden="true" />{translate('people.archiveButton')}</button></div>
    <dl className="record-facts">
      <div><dt>{translate('people.preferredName')}</dt><dd>{person.preferred_name || '—'}</dd></div>
      <div><dt>{translate('people.relationship')}</dt><dd>{person.kind === 'employee' ? translate('people.employee') : translate('people.contact')}</dd></div>
      <div><dt>{translate('people.role')}</dt><dd>{person.role || '—'}</dd></div>
      <div><dt>{translate('people.responsibility')}</dt><dd>{person.responsibility || '—'}</dd></div>
      <div><dt>{translate('people.site')}</dt><dd>{person.location || '—'}</dd></div>
      <div><dt>{translate('people.location')}</dt><dd>{person.office || '—'}</dd></div>
      <div><dt>{translate('people.phone')}</dt><dd>{person.phone ? <a href={`tel:${person.phone}`}>{person.phone}</a> : '—'}</dd></div>
      <div><dt>{translate('people.email')}</dt><dd>{person.email ? <a href={`mailto:${person.email}`}>{person.email}</a> : '—'}</dd></div>
    </dl>
  </div>
}

function cellValue(person: PersonRecord, column: PersonColumn) {
  if (column === 'kind') return person.kind === 'employee' ? translate('people.employee') : translate('people.contact')
  const value = person[column]
  if (!value) return '—'
  if (column === 'email') return <a href={`mailto:${value}`}>{value}</a>
  if (column === 'phone') return <a href={`tel:${value}`}>{value}</a>
  return value
}

export function People({ workspace, client = browserPeopleClient, sitesClient = browserSitesClient }: { workspace: WorkspaceContext | null; client?: PeopleClient; sitesClient?: SitesClient }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const scope = useMemo(() => ({ organizationId: workspace?.id }), [workspace?.id])
  const scopeKey = workspace?.id ?? 'msp'
  const workspaceName = workspace?.name ?? translate('people.mspWorkspace')
  const [query, setQuery] = useState<PeopleQuery>(initialQuery)
  const [loaded, setLoaded] = useState<{ scopeKey: string; result: Awaited<ReturnType<PeopleClient['list']>> } | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const drawerId = searchParams.get('person')
  const [selected, setSelected] = useState<{ scopeKey: string; record: PersonRecord } | null>(null)
  const [drawerErrorId, setDrawerErrorId] = useState<string | null>(null)
  const [drawerMode, setDrawerMode] = useState<'view' | 'edit'>('view')
  const [dirty, setDirty] = useState(false)
  const [confirmingClose, setConfirmingClose] = useState(false)
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

  const updateDrawerUrl = useCallback((id: string | null, replace = false) => {
    const next = new URLSearchParams(searchParams)
    if (id) next.set('person', id)
    else next.delete('person')
    setSearchParams(next, { replace })
  }, [searchParams, setSearchParams])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.list(scope, query, controller.signal)
        .then((result) => { if (!controller.signal.aborted) { setLoaded({ scopeKey, result }); setPhase('ready'); setError(null) } })
        .catch((loadError: unknown) => { if (!controller.signal.aborted) { setPhase('error'); setError(errorMessage(loadError, translate('people.loadFailed'))) } })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, query, revision, scope, scopeKey])

  useEffect(() => {
    const controller = new AbortController()
    sitesClient.list(scope, placementSiteQuery, controller.signal)
      .then((result) => { if (!controller.signal.aborted) { setPlacementSites({ scopeKey, sites: result.results }); setSitesErrorScopeKey(null) } })
      .catch(() => { if (!controller.signal.aborted) { setPlacementSites(null); setSitesErrorScopeKey(scopeKey) } })
    return () => controller.abort()
  }, [scope, scopeKey, sitesClient, revision])

  const result = loaded?.scopeKey === scopeKey ? loaded.result : null
  const visiblePhase = loaded && loaded.scopeKey !== scopeKey ? 'loading' : phase
  const sites = placementSites?.scopeKey === scopeKey ? placementSites.sites : []
  const sitesUnavailable = sitesErrorScopeKey === scopeKey
  const listedPerson = drawerId && drawerId !== 'new' ? result?.results.find((record) => record.id === drawerId) : null
  const drawerRecord = listedPerson ?? (selected?.scopeKey === scopeKey && selected.record.id === drawerId ? selected.record : null)
  const drawerPhase = drawerErrorId === drawerId ? 'error' : drawerRecord || drawerId === 'new' ? 'ready' : 'loading'

  useEffect(() => {
    if (!drawerId || drawerId === 'new' || listedPerson) return
    const controller = new AbortController()
    client.retrieve(scope, drawerId, controller.signal)
      .then((record) => { if (!controller.signal.aborted) { setSelected({ scopeKey, record }); setDrawerErrorId(null) } })
      .catch(() => { if (!controller.signal.aborted) setDrawerErrorId(drawerId) })
    return () => controller.abort()
  }, [client, drawerId, listedPerson, scope, scopeKey])

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

  const personFilterLabel = query.filter_field
    ? `${columnLabels[query.filter_field]}${query.filter_value ? `: ${query.filter_value}` : ''}`
    : translate('people.noFieldFilter')

  const openPerson = (person: PersonRecord, mode: 'view' | 'edit' = 'view') => {
    setSelected({ scopeKey, record: person })
    setDrawerErrorId(null)
    setDrawerMode(mode)
    setArchiving(null)
    setError(null)
    setMessage(null)
    updateDrawerUrl(person.id)
  }

  const finishClose = () => {
    setDirty(false)
    setConfirmingClose(false)
    setArchiving(null)
    setError(null)
    setDrawerMode('view')
    updateDrawerUrl(null)
  }

  const closeDrawer = () => {
    if (saving) return
    if (dirty) { setConfirmingClose(true); return }
    finishClose()
  }

  const save = async (input: PersonInput) => {
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const creating = drawerId === 'new'
      const saved = creating ? await client.create(scope, input) : await client.update(scope, drawerId!, input)
      setSelected({ scopeKey, record: saved })
      setDirty(false)
      setDrawerMode('view')
      updateDrawerUrl(saved.id, creating)
      setMessage(creating ? translate('people.added', { name: input.full_name }) : translate('people.updated', { name: input.full_name }))
      setRevision((value) => value + 1)
    } catch (saveError) {
      setError(errorMessage(saveError, translate('people.saveFailed')))
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
      if (drawerId === archiving.id) updateDrawerUrl(null)
      setMessage(translate('people.archived', { name: archiving.full_name, workspace: workspaceName }))
      setRevision((value) => value + 1)
    } catch (archiveError) {
      setError(errorMessage(archiveError, translate('people.archiveFailed')))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <header className="page-header"><div><h1>{translate('people.heading')}</h1></div><button className="primary-button" type="button" aria-label={translate('people.new')} title={translate('people.new')} onClick={() => { setSelected(null); setDrawerMode('edit'); setArchiving(null); setError(null); setMessage(null); updateDrawerUrl('new') }}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('people.new')}</span></button></header>
      {error && !drawerId && <div className="form-error people-error" role="alert">{error}</div>}
      {message && !drawerId && <div className="form-success" role="status">{message}</div>}
      {drawerId && <QuickDrawer title={drawerId === 'new' ? translate('people.add') : drawerRecord?.full_name ?? translate('people.record')} onClose={closeDrawer} returnFocusId={drawerId === 'new' ? undefined : `person-row-${drawerId}`} returnHref={workspace ? `/workspaces/organizations/${workspace.id}/people` : '/people'} returnLabel={translate('people.back')}>
        {error && <div className="form-error" role="alert">{error}</div>}
        {message && <div className="form-success" role="status">{message}</div>}
        {drawerPhase === 'loading' && <p className="people-state" role="status">{translate('people.recordLoading')}</p>}
        {drawerPhase === 'error' && <div className="form-error" role="alert">{translate('people.recordUnavailable')}</div>}
        {drawerPhase === 'ready' && (drawerId === 'new' || drawerRecord) && (drawerId === 'new' || drawerMode === 'edit'
          ? <PersonForm key={drawerId} person={drawerId === 'new' ? null : drawerRecord!} workspaceName={workspaceName} sites={sites} sitesUnavailable={sitesUnavailable} saving={saving} onCancel={drawerId === 'new' ? closeDrawer : () => { setDirty(false); setError(null); setDrawerMode('view') }} onDirtyChange={setDirty} onSave={save} />
          : <PersonOverview person={drawerRecord!} onEdit={() => setDrawerMode('edit')} onArchive={() => setArchiving(drawerRecord)} />)}
        {confirmingClose && <div className="archive-confirmation" role="alertdialog" aria-labelledby="people-unsaved-heading" aria-describedby="people-unsaved-description"><div><strong id="people-unsaved-heading">{translate('navigation.unsaved.title')}</strong><p id="people-unsaved-description">{translate('navigation.unsaved.description')}</p></div><div className="form-actions"><button autoFocus className="primary-button" type="button" onClick={() => setConfirmingClose(false)}>{translate('navigation.unsaved.keep')}</button><button className="secondary-button" type="button" onClick={finishClose}>{translate('navigation.unsaved.discard')}</button></div></div>}
        {archiving && drawerId && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-person-drawer-heading"><div><strong id="archive-person-drawer-heading">{translate('people.archiveQuestion', { name: archiving.full_name })}</strong><p>{translate('people.archiveHelp', { workspace: workspaceName })}</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? translate('common.archiving') : translate('people.archiveButton')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setArchiving(null)}>{translate('common.cancel')}</button></div></div>}
      </QuickDrawer>}
      <section className="content-section people-list-section" aria-labelledby="people-list-heading">
        <div className="section-heading people-list-heading"><h2 id="people-list-heading">{translate('people.directory')}</h2><span>{result ? translate(result.count === 1 ? 'people.countOne' : 'people.countMany', { count: result.count }) : translate('common.loading')}</span></div>
        <div className="people-toolbar">
          <label className="people-search"><Search size={16} aria-hidden="true" /><span className="sr-only">{translate('people.searchAll')}</span><input type="search" aria-label={translate('people.searchAll')} value={query.q} onChange={(event) => changeQuery({ q: event.target.value })} placeholder={translate('people.searchPlaceholder')} /></label>
          <FilterMenu groups={[{
            kind: 'custom',
            label: translate('people.personField'),
            valueLabel: personFilterLabel,
            content: <div className="filter-menu-custom">
              <label>{translate('people.filterField')}<select aria-label={translate('people.filterField')} value={query.filter_field} onChange={(event) => changeQuery({ filter_field: event.target.value as PersonFilterField | '', filter_value: '' })}><option value="">{translate('people.noFieldFilter')}</option>{optionalColumns.map((column) => <option key={column} value={column}>{columnLabels[column]}</option>)}</select></label>
              <label>{translate('people.filterValue')}<input aria-label={translate('people.filterValue')} value={query.filter_value} disabled={!query.filter_field} onChange={(event) => changeQuery({ filter_value: event.target.value })} placeholder={query.filter_field ? translate('people.filterPlaceholder', { field: columnLabels[query.filter_field].toLowerCase() }) : translate('people.chooseField')} /></label>
            </div>,
          }]} activeCount={query.filter_field || query.filter_value ? 1 : 0} onClear={() => changeQuery({ filter_field: '', filter_value: '' })} menuLabel={translate('people.filters')} />
          <div className="column-settings" ref={settingsRef}>
            <button className="secondary-button column-settings-trigger" type="button" aria-label={translate('people.chooseColumns')} title={translate('people.chooseColumns')} aria-expanded={columnsOpen} onClick={() => setColumnsOpen((open) => !open)}><Settings2 size={16} aria-hidden="true" /></button>
            {columnsOpen && <fieldset className="column-settings-popover"><legend>{translate('people.visibleColumns')}</legend>{optionalColumns.map((column) => <label key={column}><input type="checkbox" checked={visibleColumns.includes(column)} onChange={() => toggleColumn(column)} />{columnLabels[column]}</label>)}</fieldset>}
          </div>
        </div>
        {visiblePhase === 'loading' && <p className="people-state" role="status">{translate('people.loading')}</p>}
        {visiblePhase === 'error' && <p className="people-state">{translate('people.unavailable')}</p>}
        {visiblePhase === 'ready' && result?.results.length === 0 && <p className="people-state">{query.q || query.filter_value ? translate('people.noMatch') : translate('people.empty')}</p>}
        {visiblePhase === 'ready' && result && result.results.length > 0 && (
          <div className="people-table-wrap" role="group" aria-label={translate('people.table')} tabIndex={0}>
            <table className="people-table">
              <thead><tr>{visibleColumns.map((column) => <th key={column} scope="col" aria-sort={query.ordering === column ? 'ascending' : query.ordering === `-${column}` ? 'descending' : 'none'}><button type="button" onClick={() => sort(column)}>{columnLabels[column]}{query.ordering === column && <ArrowUp size={13} aria-hidden="true" />}{query.ordering === `-${column}` && <ArrowDown size={13} aria-hidden="true" />}</button></th>)}<th scope="col"><span className="sr-only">{translate('common.actions')}</span></th></tr></thead>
              <tbody>{result.results.map((person) => <tr key={person.association_id}>{visibleColumns.map((column) => <td key={column} data-label={columnLabels[column]}>{column === 'full_name' ? <button id={`person-row-${person.id}`} className="collection-name" type="button" onClick={() => openPerson(person)}>{person.full_name}</button> : cellValue(person, column)}</td>)}<td className="people-row-actions"><button className="row-action" type="button" aria-label={translate('people.edit', { name: person.full_name })} onClick={() => openPerson(person, 'edit')}><Pencil size={15} aria-hidden="true" />{translate('common.edit')}</button><button className="row-action danger" type="button" aria-label={translate('people.archive', { name: person.full_name })} onClick={() => { setArchiving(person); setMessage(null) }}><Trash2 size={15} aria-hidden="true" />{translate('common.archive')}</button></td></tr>)}</tbody>
            </table>
          </div>
        )}
        {visiblePhase === 'ready' && result && result.count > result.page_size && <nav className="people-pagination" aria-label={translate('people.pages')}><button className="secondary-button" type="button" disabled={result.page === 1} onClick={() => changeQuery({ page: result.page - 1 })}><ChevronLeft size={15} aria-hidden="true" />{translate('common.previous')}</button><span>{translate('common.pageNumber', { page: result.page })}</span><button className="secondary-button" type="button" disabled={!result.has_more} onClick={() => changeQuery({ page: result.page + 1 })}>{translate('common.next')}<ChevronRight size={15} aria-hidden="true" /></button></nav>}
        {archiving && !drawerId && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-person-heading"><div><strong id="archive-person-heading">{translate('people.archiveQuestion', { name: archiving.full_name })}</strong><p>{translate('people.archiveHelp', { workspace: workspaceName })}</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? translate('common.archiving') : translate('people.archiveButton')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setArchiving(null)}>{translate('common.cancel')}</button></div></div>}
      </section>
    </>
  )
}
