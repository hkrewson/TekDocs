import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Ellipsis, ListPlus, MapPin, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { translate } from '../i18n/localization'
import { EntityCustomFields } from '../custom-fields/EntityCustomFields'
import { browserCustomFieldsClient } from '../custom-fields/api'
import type { CustomFieldsClient } from '../custom-fields/api'
import type { WorkspaceContext } from '../workspaces/api'
import { browserSitesClient } from './api'
import type { LocationInput, LocationKind, LocationRecord, SiteInput, SiteRecord, SitesClient } from './api'

const emptySite: SiteInput = { name: '', code: '', address_line_1: '', address_line_2: '', city: '', region: '', postal_code: '', country_code: '', timezone: '', phone: '' }
const kindLabels: Record<LocationKind, string> = {
  building: translate('sites.typeBuilding'), floor: translate('sites.typeFloor'), suite: translate('sites.typeSuite'), room: translate('sites.typeRoom'),
  office: translate('sites.typeOffice'), desk: translate('sites.typeDesk'), area: translate('sites.typeArea'),
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

function SiteForm({ site, saving, onCancel, onSave }: { site: SiteRecord | null; saving: boolean; onCancel: () => void; onSave: (input: SiteInput) => Promise<void> }) {
  const [input, setInput] = useState<SiteInput>(() => site ? {
    name: site.name, code: site.code, address_line_1: site.address_line_1, address_line_2: site.address_line_2, city: site.city, region: site.region, postal_code: site.postal_code, country_code: site.country_code, timezone: site.timezone, phone: site.phone,
  } : emptySite)
  const submit = (event: FormEvent) => { event.preventDefault(); void onSave(input) }
  return (
    <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="site-form-heading">
      <form className="record-form record-form-grid site-form record-form-wide" onSubmit={submit}>
        <div className="section-heading"><h2 id="site-form-heading">{site ? translate('sites.editSite', { name: site.name }) : translate('sites.addSite')}</h2></div>
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
    </section>
  )
}

function LocationForm({ site, location, saving, onCancel, onSave }: { site: SiteRecord; location: LocationRecord | null; saving: boolean; onCancel: () => void; onSave: (input: LocationInput) => Promise<void> }) {
  const [input, setInput] = useState<LocationInput>(() => location ? { name: location.name, kind: location.kind, code: location.code, parent_id: location.parent_id } : { name: '', kind: 'room', code: '', parent_id: null })
  const submit = (event: FormEvent) => { event.preventDefault(); void onSave(input) }
  return (
    <form className="location-form" onSubmit={submit} aria-label={location ? translate('sites.editLocation', { name: location.name }) : translate('sites.addLocationTo', { name: site.name })}>
      <label>{translate('sites.locationName')}<input autoFocus required maxLength={240} value={input.name} onChange={(event) => setInput({ ...input, name: event.target.value })} /></label>
      <label>{translate('sites.locationType')}<select value={input.kind} onChange={(event) => setInput({ ...input, kind: event.target.value as LocationKind })}>{Object.entries(kindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>{translate('sites.inside')}<select value={input.parent_id ?? ''} onChange={(event) => setInput({ ...input, parent_id: event.target.value || null })}><option value="">{translate('sites.topLevel')}</option>{site.locations.filter((item) => item.id !== location?.id).map((item) => <option key={item.id} value={item.id}>{item.name} ({kindLabels[item.kind]})</option>)}</select></label>
      <label>{translate('sites.internalCode')} <span>{translate('common.optional')}</span><input maxLength={64} value={input.code} onChange={(event) => setInput({ ...input, code: event.target.value })} /></label>
      <div className="form-actions"><button className="primary-button" type="submit" disabled={saving}>{saving ? translate('common.saving') : translate('sites.saveLocation')}</button><button className="secondary-button" type="button" disabled={saving} onClick={onCancel}>{translate('common.cancel')}</button></div>
    </form>
  )
}

function locationRows(locations: LocationRecord[]) {
  const children = new Map<string | null, LocationRecord[]>()
  for (const location of locations) children.set(location.parent_id, [...(children.get(location.parent_id) ?? []), location])
  const result: { location: LocationRecord; depth: number }[] = []
  const visit = (parentId: string | null, depth: number) => {
    for (const location of children.get(parentId) ?? []) {
      result.push({ location, depth })
      visit(location.id, depth + 1)
    }
  }
  visit(null, 0)
  for (const location of locations) if (!result.some((item) => item.location.id === location.id)) result.push({ location, depth: 0 })
  return result
}

function address(site: SiteRecord) {
  return [site.address_line_1, site.address_line_2, [site.city, site.region, site.postal_code].filter(Boolean).join(', '), site.country_code].filter(Boolean).join(' · ')
}

export function Sites({ workspace, client = browserSitesClient, customFieldsClient = browserCustomFieldsClient }: { workspace: WorkspaceContext | null; client?: SitesClient; customFieldsClient?: CustomFieldsClient }) {
  const scope = useMemo(() => ({ organizationId: workspace?.id }), [workspace?.id])
  const scopeKey = workspace?.id ?? 'msp'
  const workspaceName = workspace?.name ?? translate('sites.mspWorkspace')
  const [query, setQuery] = useState('')
  const [loaded, setLoaded] = useState<{ scopeKey: string; result: Awaited<ReturnType<SitesClient['list']>> } | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [editingSite, setEditingSite] = useState<SiteRecord | 'new' | null>(null)
  const [editingLocation, setEditingLocation] = useState<{ site: SiteRecord; location: LocationRecord | null } | null>(null)
  const [archiving, setArchiving] = useState<{ site: SiteRecord; location?: LocationRecord } | null>(null)
  const [customFieldTarget, setCustomFieldTarget] = useState<{ id: string; name: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)

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
  const refresh = (notice: string) => { setEditingSite(null); setEditingLocation(null); setArchiving(null); setCustomFieldTarget(null); setMessage(notice); setRevision((value) => value + 1) }

  const saveSite = async (input: SiteInput) => {
    setSaving(true); setError(null); setMessage(null)
    try {
      if (editingSite === 'new') await client.create(scope, input)
      else await client.update(scope, editingSite!.id, input)
      refresh(editingSite === 'new' ? translate('sites.siteAdded', { name: input.name }) : translate('sites.siteUpdated', { name: input.name }))
    } catch (saveError) { setError(errorMessage(saveError, translate('sites.saveSiteFailed'))) } finally { setSaving(false) }
  }
  const saveLocation = async (input: LocationInput) => {
    if (!editingLocation) return
    setSaving(true); setError(null); setMessage(null)
    try {
      if (editingLocation.location) await client.updateLocation(scope, editingLocation.site.id, editingLocation.location.id, input)
      else await client.createLocation(scope, editingLocation.site.id, input)
      refresh(editingLocation.location ? translate('sites.locationUpdated', { name: input.name }) : translate('sites.locationAdded', { name: input.name }))
    } catch (saveError) { setError(errorMessage(saveError, translate('sites.saveLocationFailed'))) } finally { setSaving(false) }
  }
  const archive = async () => {
    if (!archiving) return
    setSaving(true); setError(null); setMessage(null)
    try {
      if (archiving.location) await client.archiveLocation(scope, archiving.site.id, archiving.location.id)
      else await client.archive(scope, archiving.site.id)
      refresh(archiving.location ? translate('sites.locationArchived', { name: archiving.location.name }) : translate('sites.siteArchived', { name: archiving.site.name }))
    } catch (archiveError) { setError(errorMessage(archiveError, translate('sites.archiveFailed'))) } finally { setSaving(false) }
  }

  return (
    <>
      <header className="page-header"><div><h1>{translate('sites.heading')}</h1></div><button className="primary-button" type="button" aria-label={translate('sites.new')} title={translate('sites.new')} onClick={() => { setEditingSite('new'); setEditingLocation(null); setArchiving(null); setCustomFieldTarget(null); setMessage(null) }}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('sites.new')}</span></button></header>
      {error && <div className="form-error people-error" role="alert">{error}</div>}
      {message && <div className="form-success" role="status">{message}</div>}
      {editingSite && <SiteForm key={editingSite === 'new' ? 'new' : editingSite.id} site={editingSite === 'new' ? null : editingSite} saving={saving} onCancel={() => setEditingSite(null)} onSave={saveSite} />}
      {customFieldTarget && <EntityCustomFields workspace={workspace} entityId={customFieldTarget.id} entityName={customFieldTarget.name} onClose={() => setCustomFieldTarget(null)} client={customFieldsClient} />}
      <section className="content-section site-list-section" aria-labelledby="site-list-heading">
        <div className="section-heading site-list-heading"><h2 id="site-list-heading">{translate('sites.locations')}</h2><span>{result ? translate(result.count === 1 ? 'sites.countOne' : 'sites.countMany', { count: result.count }) : translate('common.loading')}</span></div>
        <label className="site-search"><Search size={16} aria-hidden="true" /><span className="sr-only">{translate('sites.search')}</span><input type="search" aria-label={translate('sites.search')} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={translate('sites.search')} /></label>
        {visiblePhase === 'loading' && <p className="people-state" role="status">{translate('sites.loading')}</p>}
        {visiblePhase === 'error' && <p className="people-state">{translate('sites.unavailable')}</p>}
        {visiblePhase === 'ready' && result?.results.length === 0 && <p className="people-state">{query ? translate('sites.noMatch') : translate('sites.empty', { workspace: workspaceName })}</p>}
        {visiblePhase === 'ready' && result && result.results.length > 0 && <div className="site-list">{result.results.map((site) => (
          <article className="site-row" key={site.id}>
            <div className="site-row-heading"><div><h3><MapPin size={16} aria-hidden="true" />{site.name}</h3><p>{address(site) || translate('sites.noAddress')}{site.code ? ` · ${site.code}` : ''}</p></div><div className="site-actions"><button className="row-action" type="button" aria-label={translate('sites.addLocationTo', { name: site.name })} onClick={() => { setEditingLocation({ site, location: null }); setEditingSite(null); setArchiving(null); setCustomFieldTarget(null) }}><Plus size={15} aria-hidden="true" />{translate('sites.location')}</button><details className="row-action-menu"><summary className="row-action" aria-label={translate('sites.moreActionsFor', { name: site.name })}><Ellipsis size={16} aria-hidden="true" /></summary><div><button type="button" aria-label={translate('sites.fieldsForSite', { name: site.name })} onClick={() => { setCustomFieldTarget({ id: site.id, name: site.name }); setEditingSite(null); setEditingLocation(null); setArchiving(null) }}><ListPlus size={15} aria-hidden="true" />{translate('sites.fields')}</button><button type="button" aria-label={translate('sites.editSite', { name: site.name })} onClick={() => { setEditingSite(site); setEditingLocation(null); setArchiving(null); setCustomFieldTarget(null) }}><Pencil size={15} aria-hidden="true" />{translate('common.edit')}</button><button className="danger" type="button" aria-label={translate('sites.archiveSite', { name: site.name })} onClick={() => { setArchiving({ site }); setEditingSite(null); setEditingLocation(null); setCustomFieldTarget(null) }}><Trash2 size={15} aria-hidden="true" />{translate('common.archive')}</button></div></details></div></div>
            {editingLocation?.site.id === site.id && <LocationForm key={editingLocation.location?.id ?? 'new'} site={site} location={editingLocation.location} saving={saving} onCancel={() => setEditingLocation(null)} onSave={saveLocation} />}
            {site.locations.length === 0 ? <p className="location-empty">{translate('sites.noLocations')}</p> : <ul className="location-tree">{locationRows(site.locations).map(({ location, depth }) => <li key={location.id} style={{ paddingLeft: 10 + depth * 22 }}><span><strong>{location.name}</strong><span>{kindLabels[location.kind]}{location.code ? ` · ${location.code}` : ''}</span></span><details className="row-action-menu"><summary className="row-action" aria-label={translate('sites.moreActionsFor', { name: location.name })}><Ellipsis size={16} aria-hidden="true" /></summary><div><button type="button" aria-label={translate('sites.fieldsForLocation', { name: location.name })} onClick={() => { setCustomFieldTarget({ id: location.id, name: location.name }); setEditingSite(null); setEditingLocation(null); setArchiving(null) }}><ListPlus size={14} aria-hidden="true" />{translate('sites.fields')}</button><button type="button" aria-label={translate('sites.editLocation', { name: location.name })} onClick={() => { setEditingLocation({ site, location }); setEditingSite(null); setArchiving(null); setCustomFieldTarget(null) }}><Pencil size={14} aria-hidden="true" />{translate('common.edit')}</button><button className="danger" type="button" aria-label={translate('sites.archiveLocation', { name: location.name })} onClick={() => { setArchiving({ site, location }); setEditingSite(null); setEditingLocation(null); setCustomFieldTarget(null) }}><Trash2 size={14} aria-hidden="true" />{translate('common.archive')}</button></div></details></li>)}</ul>}
          </article>
        ))}</div>}
        {archiving && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-place-heading"><div><strong id="archive-place-heading">{translate('sites.archiveQuestion', { name: archiving.location?.name ?? archiving.site.name })}</strong><p>{archiving.location ? translate('sites.archiveLocationHelp') : translate('sites.archiveSiteHelp')}</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? translate('common.archiving') : translate('common.archive')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setArchiving(null)}>{translate('common.cancel')}</button></div></div>}
      </section>
    </>
  )
}
