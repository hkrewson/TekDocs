import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Ellipsis, ListPlus, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { QuickDrawer } from '../collections/QuickDrawer'
import '../collections/collections.css'
import { translate } from '../i18n/localization'
import { EntityCustomFields } from '../custom-fields/EntityCustomFields'
import { browserCustomFieldsClient } from '../custom-fields/api'
import type { CustomFieldsClient } from '../custom-fields/api'
import type { WorkspaceContext } from '../workspaces/api'
import { browserSitesClient } from './api'
import type { LocationInput, LocationKind, LocationRecord, SiteInput, SiteOrdering, SiteRecord, SitesClient, SitesQuery } from './api'

const emptySite: SiteInput = { name: '', code: '', address_line_1: '', address_line_2: '', city: '', region: '', postal_code: '', country_code: '', timezone: '', phone: '' }
const initialQuery: SitesQuery = { q: '', ordering: 'name', page: 1, page_size: 25 }
const kindLabels: Record<LocationKind, string> = {
  building: translate('sites.typeBuilding'), floor: translate('sites.typeFloor'), suite: translate('sites.typeSuite'), room: translate('sites.typeRoom'),
  office: translate('sites.typeOffice'), desk: translate('sites.typeDesk'), area: translate('sites.typeArea'),
}

function errorMessage(error: unknown, fallback: string) { return error instanceof Error ? error.message : fallback }
function address(site: SiteRecord) { return [site.address_line_1, site.address_line_2, [site.city, site.region, site.postal_code].filter(Boolean).join(', '), site.country_code].filter(Boolean).join(' · ') }
function siteInput(site: SiteRecord | null): SiteInput { return site ? { name: site.name, code: site.code, address_line_1: site.address_line_1, address_line_2: site.address_line_2, city: site.city, region: site.region, postal_code: site.postal_code, country_code: site.country_code, timezone: site.timezone, phone: site.phone } : emptySite }

function SiteForm({ site, saving, onCancel, onDirtyChange, onSave }: { site: SiteRecord | null; saving: boolean; onCancel: () => void; onDirtyChange: (dirty: boolean) => void; onSave: (input: SiteInput) => Promise<void> }) {
  const initial = useMemo(() => siteInput(site), [site])
  const [input, setInput] = useState<SiteInput>(initial)
  useEffect(() => { onDirtyChange(JSON.stringify(input) !== JSON.stringify(initial)); return () => onDirtyChange(false) }, [initial, input, onDirtyChange])
  const submit = (event: FormEvent) => { event.preventDefault(); void onSave(input) }
  return <form className="record-form record-form-grid site-form record-form-wide operational-record-form" onSubmit={submit}>
    <label>{translate('sites.siteName')}<input autoFocus required maxLength={240} value={input.name} onChange={(event) => setInput({ ...input, name: event.target.value })} /></label>
    <label>{translate('sites.internalCode')} <span>{translate('common.optional')}</span><input maxLength={64} value={input.code} onChange={(event) => setInput({ ...input, code: event.target.value })} /></label>
    <label className="site-form-wide">{translate('sites.address')}<input maxLength={240} value={input.address_line_1} onChange={(event) => setInput({ ...input, address_line_1: event.target.value })} /></label>
    <label className="site-form-wide">{translate('sites.addressLine2')} <span>{translate('common.optional')}</span><input maxLength={240} value={input.address_line_2} onChange={(event) => setInput({ ...input, address_line_2: event.target.value })} /></label>
    <label>{translate('sites.city')}<input maxLength={120} value={input.city} onChange={(event) => setInput({ ...input, city: event.target.value })} /></label>
    <label>{translate('sites.region')}<input maxLength={120} value={input.region} onChange={(event) => setInput({ ...input, region: event.target.value })} /></label>
    <label>{translate('sites.postalCode')}<input maxLength={32} value={input.postal_code} onChange={(event) => setInput({ ...input, postal_code: event.target.value })} /></label>
    <label>{translate('sites.countryCode')} <span>{translate('sites.countryCodeHelp')}</span><input maxLength={2} pattern="[A-Za-z]{2}" value={input.country_code} onChange={(event) => setInput({ ...input, country_code: event.target.value.toUpperCase() })} /></label>
    <label>{translate('sites.timezone')} <span>{translate('sites.timezoneHelp')}</span><input maxLength={64} value={input.timezone} onChange={(event) => setInput({ ...input, timezone: event.target.value })} /></label>
    <label>{translate('sites.phone')} <span>{translate('common.optional')}</span><input type="tel" maxLength={64} value={input.phone} onChange={(event) => setInput({ ...input, phone: event.target.value })} /></label>
    <div className="form-actions"><button className="primary-button" type="submit" disabled={saving}>{saving ? translate('common.saving') : translate('sites.saveSite')}</button><button className="secondary-button" type="button" disabled={saving} onClick={onCancel}>{translate('common.cancel')}</button></div>
  </form>
}

function LocationForm({ site, location, saving, onCancel, onDirtyChange, onSave }: { site: SiteRecord; location: LocationRecord | null; saving: boolean; onCancel: () => void; onDirtyChange: (dirty: boolean) => void; onSave: (input: LocationInput) => Promise<void> }) {
  const initial = useMemo<LocationInput>(() => location ? { name: location.name, kind: location.kind, code: location.code, parent_id: location.parent_id } : { name: '', kind: 'room', code: '', parent_id: null }, [location])
  const [input, setInput] = useState<LocationInput>(initial)
  useEffect(() => { onDirtyChange(JSON.stringify(input) !== JSON.stringify(initial)); return () => onDirtyChange(false) }, [initial, input, onDirtyChange])
  const submit = (event: FormEvent) => { event.preventDefault(); void onSave(input) }
  return <form className="location-form" onSubmit={submit} aria-label={location ? translate('sites.editLocation', { name: location.name }) : translate('sites.addLocationTo', { name: site.name })}>
    <label>{translate('sites.locationName')}<input autoFocus required maxLength={240} value={input.name} onChange={(event) => setInput({ ...input, name: event.target.value })} /></label>
    <label>{translate('sites.locationType')}<select value={input.kind} onChange={(event) => setInput({ ...input, kind: event.target.value as LocationKind })}>{Object.entries(kindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <label>{translate('sites.inside')}<select value={input.parent_id ?? ''} onChange={(event) => setInput({ ...input, parent_id: event.target.value || null })}><option value="">{translate('sites.topLevel')}</option>{site.locations.filter((item) => item.id !== location?.id).map((item) => <option key={item.id} value={item.id}>{item.name} ({kindLabels[item.kind]})</option>)}</select></label>
    <label>{translate('sites.internalCode')} <span>{translate('common.optional')}</span><input maxLength={64} value={input.code} onChange={(event) => setInput({ ...input, code: event.target.value })} /></label>
    <div className="form-actions"><button className="primary-button" type="submit" disabled={saving}>{saving ? translate('common.saving') : translate('sites.saveLocation')}</button><button className="secondary-button" type="button" disabled={saving} onClick={onCancel}>{translate('common.cancel')}</button></div>
  </form>
}

function locationRows(locations: LocationRecord[]) {
  const children = new Map<string | null, LocationRecord[]>()
  for (const location of locations) children.set(location.parent_id, [...(children.get(location.parent_id) ?? []), location])
  const result: { location: LocationRecord; depth: number }[] = []
  const visit = (parentId: string | null, depth: number) => { for (const location of children.get(parentId) ?? []) { result.push({ location, depth }); visit(location.id, depth + 1) } }
  visit(null, 0)
  for (const location of locations) if (!result.some((item) => item.location.id === location.id)) result.push({ location, depth: 0 })
  return result
}

function locationBranchIds(locations: LocationRecord[], rootId: string) {
  const ids = new Set([rootId])
  let changed = true
  while (changed) {
    changed = false
    for (const location of locations) {
      if (location.parent_id && ids.has(location.parent_id) && !ids.has(location.id)) {
        ids.add(location.id)
        changed = true
      }
    }
  }
  return ids
}

function queryFromParams(parameters: URLSearchParams): SitesQuery {
  const ordering = parameters.get('site_order') as SiteOrdering | null
  const page = Number(parameters.get('site_page'))
  return { ...initialQuery, q: parameters.get('q') ?? '', ordering: ordering ?? 'name', page: Number.isInteger(page) && page > 0 ? page : 1 }
}

export function Sites({ workspace, client = browserSitesClient, customFieldsClient = browserCustomFieldsClient }: { workspace: WorkspaceContext | null; client?: SitesClient; customFieldsClient?: CustomFieldsClient }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const scope = useMemo(() => ({ organizationId: workspace?.id }), [workspace?.id])
  const scopeKey = workspace?.id ?? 'msp'
  const workspaceName = workspace?.name ?? translate('sites.mspWorkspace')
  const [query, setQuery] = useState<SitesQuery>(() => queryFromParams(searchParams))
  const [loaded, setLoaded] = useState<{ scopeKey: string; result: Awaited<ReturnType<SitesClient['list']>> } | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const drawerId = searchParams.get('site')
  const [selected, setSelected] = useState<{ scopeKey: string; record: SiteRecord } | null>(null)
  const [drawerErrorId, setDrawerErrorId] = useState<string | null>(null)
  const [drawerMode, setDrawerMode] = useState<'view' | 'edit'>('view')
  const [editingLocation, setEditingLocation] = useState<LocationRecord | 'new' | null>(null)
  const [archiving, setArchiving] = useState<{ site: SiteRecord; location?: LocationRecord } | null>(null)
  const [customFieldTarget, setCustomFieldTarget] = useState<{ id: string; name: string } | null>(null)
  const [dirty, setDirty] = useState(false)
  const [confirmingClose, setConfirmingClose] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)

  const updateDrawerUrl = useCallback((id: string | null, replace = false) => {
    const next = new URLSearchParams(searchParams)
    if (id) next.set('site', id); else next.delete('site')
    setSearchParams(next, { replace })
  }, [searchParams, setSearchParams])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.list(scope, query, controller.signal)
        .then((result) => { if (!controller.signal.aborted) { setLoaded({ scopeKey, result }); setPhase('ready'); setError(null) } })
        .catch((loadError: unknown) => { if (!controller.signal.aborted) { setPhase('error'); setError(errorMessage(loadError, translate('sites.loadFailed'))) } })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, query, revision, scope, scopeKey])

  const result = loaded?.scopeKey === scopeKey ? loaded.result : null
  const visiblePhase = loaded && loaded.scopeKey !== scopeKey ? 'loading' : phase
  const listedSite = drawerId && drawerId !== 'new' ? result?.results.find((record) => record.id === drawerId) : null
  const drawerRecord = (selected?.scopeKey === scopeKey && selected.record.id === drawerId ? selected.record : null) ?? listedSite
  const drawerPhase = drawerErrorId === drawerId ? 'error' : drawerRecord || drawerId === 'new' ? 'ready' : 'loading'

  useEffect(() => {
    if (!drawerId || drawerId === 'new' || listedSite) return
    const controller = new AbortController()
    client.retrieve(scope, drawerId, controller.signal)
      .then((record) => { if (!controller.signal.aborted) { setSelected({ scopeKey, record }); setDrawerErrorId(null) } })
      .catch(() => { if (!controller.signal.aborted) setDrawerErrorId(drawerId) })
    return () => controller.abort()
  }, [client, drawerId, listedSite, scope, scopeKey])

  const changeQuery = (changes: Partial<SitesQuery>) => {
    const nextQuery = { ...query, ...changes, page: changes.page ?? 1 }
    const nextParams = new URLSearchParams(searchParams)
    if (nextQuery.q) nextParams.set('q', nextQuery.q); else nextParams.delete('q')
    if (nextQuery.ordering !== 'name') nextParams.set('site_order', nextQuery.ordering); else nextParams.delete('site_order')
    if (nextQuery.page > 1) nextParams.set('site_page', String(nextQuery.page)); else nextParams.delete('site_page')
    setQuery(nextQuery); setSearchParams(nextParams, { replace: true })
  }
  const sort = (field: 'name' | 'timezone') => changeQuery({ ordering: query.ordering === field ? `-${field}` : field })
  const sortIndicator = (field: string) => query.ordering === field ? <ArrowUp size={13} aria-hidden="true" /> : query.ordering === `-${field}` ? <ArrowDown size={13} aria-hidden="true" /> : null

  const openSite = (site: SiteRecord, mode: 'view' | 'edit' = 'view') => { setSelected({ scopeKey, record: site }); setDrawerErrorId(null); setDrawerMode(mode); setEditingLocation(null); setArchiving(null); setCustomFieldTarget(null); setError(null); setMessage(null); updateDrawerUrl(site.id) }
  const finishClose = () => { setDirty(false); setConfirmingClose(false); setEditingLocation(null); setArchiving(null); setCustomFieldTarget(null); setError(null); setDrawerMode('view'); updateDrawerUrl(null) }
  const closeDrawer = () => { if (saving) return; if (dirty) { setConfirmingClose(true); return } finishClose() }

  const saveSite = async (input: SiteInput) => {
    setSaving(true); setError(null); setMessage(null)
    try {
      const creating = drawerId === 'new'
      const saved = creating ? await client.create(scope, input) : await client.update(scope, drawerId!, input)
      setSelected({ scopeKey, record: saved }); setDirty(false); setDrawerMode('view'); updateDrawerUrl(saved.id, creating)
      setMessage(creating ? translate('sites.siteAdded', { name: input.name }) : translate('sites.siteUpdated', { name: input.name })); setRevision((value) => value + 1)
    } catch (saveError) { setError(errorMessage(saveError, translate('sites.saveSiteFailed'))) } finally { setSaving(false) }
  }
  const saveLocation = async (input: LocationInput) => {
    if (!drawerRecord || !editingLocation) return
    setSaving(true); setError(null); setMessage(null)
    try {
      const created = editingLocation === 'new'
      const saved = created ? await client.createLocation(scope, drawerRecord.id, input) : await client.updateLocation(scope, drawerRecord.id, editingLocation.id, input)
      setSelected({ scopeKey, record: { ...drawerRecord, locations: [...drawerRecord.locations.filter((item) => item.id !== saved.id), saved] } }); setDirty(false); setEditingLocation(null)
      setMessage(created ? translate('sites.locationAdded', { name: input.name }) : translate('sites.locationUpdated', { name: input.name })); setRevision((value) => value + 1)
    } catch (saveError) { setError(errorMessage(saveError, translate('sites.saveLocationFailed'))) } finally { setSaving(false) }
  }
  const archive = async () => {
    if (!archiving) return
    setSaving(true); setError(null); setMessage(null)
    try {
      if (archiving.location) {
        await client.archiveLocation(scope, archiving.site.id, archiving.location.id)
        const archivedIds = locationBranchIds(archiving.site.locations, archiving.location.id)
        setSelected({ scopeKey, record: { ...archiving.site, locations: archiving.site.locations.filter((item) => !archivedIds.has(item.id)) } }); setMessage(translate('sites.locationArchived', { name: archiving.location.name }))
      } else { await client.archive(scope, archiving.site.id); updateDrawerUrl(null); setMessage(translate('sites.siteArchived', { name: archiving.site.name })) }
      setArchiving(null); setRevision((value) => value + 1)
    } catch (archiveError) { setError(errorMessage(archiveError, translate('sites.archiveFailed'))) } finally { setSaving(false) }
  }

  return <>
    <header className="page-header"><div><h1>{translate('sites.heading')}</h1></div><button className="primary-button" type="button" aria-label={translate('sites.new')} title={translate('sites.new')} onClick={() => { setSelected(null); setDrawerMode('edit'); setEditingLocation(null); setArchiving(null); setError(null); setMessage(null); updateDrawerUrl('new') }}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('sites.new')}</span></button></header>
    {error && !drawerId && <div className="form-error people-error" role="alert">{error}</div>}{message && !drawerId && <div className="form-success" role="status">{message}</div>}
    {drawerId && <QuickDrawer title={drawerId === 'new' ? translate('sites.addSite') : drawerRecord?.name ?? translate('sites.record')} onClose={closeDrawer} returnFocusId={drawerId === 'new' ? undefined : `site-row-${drawerId}`} returnHref={workspace ? `/workspaces/organizations/${workspace.id}/sites` : '/sites'} returnLabel={translate('sites.back')}>
      {error && <div className="form-error" role="alert">{error}</div>}{message && <div className="form-success" role="status">{message}</div>}
      {drawerPhase === 'loading' && <p className="people-state" role="status">{translate('sites.recordLoading')}</p>}{drawerPhase === 'error' && <div className="form-error" role="alert">{translate('sites.recordUnavailable')}</div>}
      {drawerPhase === 'ready' && (drawerId === 'new' || drawerRecord) && (drawerId === 'new' || drawerMode === 'edit') && <SiteForm key={drawerId} site={drawerId === 'new' ? null : drawerRecord!} saving={saving} onCancel={drawerId === 'new' ? closeDrawer : () => { setDirty(false); setError(null); setDrawerMode('view') }} onDirtyChange={setDirty} onSave={saveSite} />}
      {drawerPhase === 'ready' && drawerId !== 'new' && drawerRecord && drawerMode === 'view' && <div className="operational-record site-record">
        <div className="operational-record-actions"><button className="primary-button" type="button" onClick={() => setDrawerMode('edit')}><Pencil size={15} aria-hidden="true" />{translate('sites.editDetails')}</button><button className="secondary-button" type="button" onClick={() => setCustomFieldTarget({ id: drawerRecord.id, name: drawerRecord.name })}><ListPlus size={15} aria-hidden="true" />{translate('sites.fields')}</button><button className="secondary-button danger" type="button" onClick={() => setArchiving({ site: drawerRecord })}><Trash2 size={15} aria-hidden="true" />{translate('common.archive')}</button></div>
        <dl className="record-facts"><div><dt>{translate('sites.internalCode')}</dt><dd>{drawerRecord.code || '—'}</dd></div><div><dt>{translate('sites.address')}</dt><dd>{address(drawerRecord) || translate('sites.noAddress')}</dd></div><div><dt>{translate('sites.timezone')}</dt><dd>{drawerRecord.timezone || '—'}</dd></div><div><dt>{translate('sites.phone')}</dt><dd>{drawerRecord.phone ? <a href={`tel:${drawerRecord.phone}`}>{drawerRecord.phone}</a> : '—'}</dd></div></dl>
        <section className="site-location-section" aria-labelledby="site-location-heading"><div className="section-heading"><div><h3 id="site-location-heading">{translate('sites.locations')}</h3><p>{translate(drawerRecord.locations.length === 1 ? 'sites.locationCountOne' : 'sites.locationCountMany', { count: drawerRecord.locations.length })}</p></div><button className="secondary-button" type="button" aria-label={translate('sites.addLocationTo', { name: drawerRecord.name })} onClick={() => { setEditingLocation('new'); setArchiving(null); setCustomFieldTarget(null) }}><Plus size={15} aria-hidden="true" />{translate('sites.location')}</button></div>
          {editingLocation && <LocationForm key={editingLocation === 'new' ? 'new' : editingLocation.id} site={drawerRecord} location={editingLocation === 'new' ? null : editingLocation} saving={saving} onCancel={() => { setDirty(false); setError(null); setEditingLocation(null) }} onDirtyChange={setDirty} onSave={saveLocation} />}
          {drawerRecord.locations.length === 0 ? <p className="location-empty">{translate('sites.noLocations')}</p> : <ul className="location-tree">{locationRows(drawerRecord.locations).map(({ location, depth }) => <li key={location.id} style={{ paddingLeft: 10 + depth * 22 }}><span><strong>{location.name}</strong><span>{kindLabels[location.kind]}{location.code ? ` · ${location.code}` : ''}</span></span><details className="row-action-menu"><summary className="row-action" aria-label={translate('sites.moreActionsFor', { name: location.name })}><Ellipsis size={16} aria-hidden="true" /></summary><div><button type="button" aria-label={translate('sites.fieldsForLocation', { name: location.name })} onClick={() => { setCustomFieldTarget({ id: location.id, name: location.name }); setEditingLocation(null); setArchiving(null) }}><ListPlus size={14} aria-hidden="true" />{translate('sites.fields')}</button><button type="button" aria-label={translate('sites.editLocation', { name: location.name })} onClick={() => { setEditingLocation(location); setArchiving(null); setCustomFieldTarget(null) }}><Pencil size={14} aria-hidden="true" />{translate('common.edit')}</button><button className="danger" type="button" aria-label={translate('sites.archiveLocation', { name: location.name })} onClick={() => { setArchiving({ site: drawerRecord, location }); setEditingLocation(null); setCustomFieldTarget(null) }}><Trash2 size={14} aria-hidden="true" />{translate('common.archive')}</button></div></details></li>)}</ul>}
        </section>
      </div>}
      {customFieldTarget && <EntityCustomFields workspace={workspace} entityId={customFieldTarget.id} entityName={customFieldTarget.name} onClose={() => setCustomFieldTarget(null)} client={customFieldsClient} />}
      {archiving && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-place-heading"><div><strong id="archive-place-heading">{translate('sites.archiveQuestion', { name: archiving.location?.name ?? archiving.site.name })}</strong><p>{archiving.location ? translate('sites.archiveLocationHelp') : translate('sites.archiveSiteHelp')}</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? translate('common.archiving') : translate('common.archive')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setArchiving(null)}>{translate('common.cancel')}</button></div></div>}
      {confirmingClose && <div className="archive-confirmation" role="alertdialog" aria-labelledby="site-unsaved-heading"><div><strong id="site-unsaved-heading">{translate('navigation.unsaved.title')}</strong><p>{translate('navigation.unsaved.description')}</p></div><div className="form-actions"><button autoFocus className="primary-button" type="button" onClick={() => setConfirmingClose(false)}>{translate('navigation.unsaved.keep')}</button><button className="secondary-button" type="button" onClick={finishClose}>{translate('navigation.unsaved.discard')}</button></div></div>}
    </QuickDrawer>}
    <section className="content-section site-list-section" aria-labelledby="site-list-heading"><div className="section-heading site-list-heading"><h2 id="site-list-heading">{translate('sites.directory')}</h2><span>{result ? translate(result.count === 1 ? 'sites.countOne' : 'sites.countMany', { count: result.count }) : translate('common.loading')}</span></div>
      <label className="site-search"><Search size={16} aria-hidden="true" /><span className="sr-only">{translate('sites.search')}</span><input type="search" aria-label={translate('sites.search')} value={query.q} onChange={(event) => changeQuery({ q: event.target.value })} placeholder={translate('sites.search')} /></label>
      {visiblePhase === 'loading' && <p className="people-state" role="status">{translate('sites.loading')}</p>}{visiblePhase === 'error' && <p className="people-state">{translate('sites.unavailable')}</p>}{visiblePhase === 'ready' && result?.results.length === 0 && <p className="people-state">{query.q ? translate('sites.noMatch') : translate('sites.empty', { workspace: workspaceName })}</p>}
      {visiblePhase === 'ready' && result && result.results.length > 0 && <div className="people-table-wrap" role="group" aria-label={translate('sites.table')} tabIndex={0}><table className="people-table site-table"><thead><tr><th scope="col" aria-sort={query.ordering === 'name' ? 'ascending' : query.ordering === '-name' ? 'descending' : 'none'}><button type="button" onClick={() => sort('name')}>{translate('sites.siteName')}{sortIndicator('name')}</button></th><th scope="col">{translate('sites.address')}</th><th scope="col" aria-sort={query.ordering === 'timezone' ? 'ascending' : query.ordering === '-timezone' ? 'descending' : 'none'}><button type="button" onClick={() => sort('timezone')}>{translate('sites.timezone')}{sortIndicator('timezone')}</button></th><th scope="col">{translate('sites.locations')}</th><th scope="col"><span className="sr-only">{translate('common.actions')}</span></th></tr></thead><tbody>{result.results.map((site) => <tr key={site.id}><td data-label={translate('sites.siteName')}><button id={`site-row-${site.id}`} className="collection-name" type="button" onClick={() => openSite(site)}>{site.name}</button>{site.code && <span className="collection-secondary">{site.code}</span>}</td><td data-label={translate('sites.address')}>{address(site) || translate('sites.noAddress')}</td><td data-label={translate('sites.timezone')}>{site.timezone || '—'}</td><td data-label={translate('sites.locations')}>{site.locations.length}</td><td className="people-row-actions"><button className="row-action" type="button" aria-label={translate('sites.editSite', { name: site.name })} onClick={() => openSite(site, 'edit')}><Pencil size={15} aria-hidden="true" />{translate('common.edit')}</button></td></tr>)}</tbody></table></div>}
      {visiblePhase === 'ready' && result && result.count > result.page_size && <nav className="people-pagination" aria-label={translate('sites.pages')}><button className="secondary-button" type="button" disabled={result.page === 1} onClick={() => changeQuery({ page: result.page - 1 })}><ChevronLeft size={15} aria-hidden="true" />{translate('common.previous')}</button><span>{translate('common.pageNumber', { page: result.page })}</span><button className="secondary-button" type="button" disabled={!result.has_more} onClick={() => changeQuery({ page: result.page + 1 })}>{translate('common.next')}<ChevronRight size={15} aria-hidden="true" /></button></nav>}
    </section>
  </>
}
