import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { ListPlus, MapPin, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { translate } from '../i18n/localization'
import { EntityCustomFields } from '../custom-fields/EntityCustomFields'
import { browserCustomFieldsClient } from '../custom-fields/api'
import type { CustomFieldsClient } from '../custom-fields/api'
import type { WorkspaceContext } from '../workspaces/api'
import { browserSitesClient } from './api'
import type { LocationInput, LocationKind, LocationRecord, SiteInput, SiteRecord, SitesClient } from './api'

const emptySite: SiteInput = { name: '', code: '', address_line_1: '', address_line_2: '', city: '', region: '', postal_code: '', country_code: '', timezone: '', phone: '' }
const kindLabels: Record<LocationKind, string> = { building: 'Building', floor: 'Floor', suite: 'Suite', room: 'Room', office: 'Office', desk: 'Desk', area: 'Area' }

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

function SiteForm({ site, saving, onCancel, onSave }: { site: SiteRecord | null; saving: boolean; onCancel: () => void; onSave: (input: SiteInput) => Promise<void> }) {
  const [input, setInput] = useState<SiteInput>(() => site ? {
    name: site.name, code: site.code, address_line_1: site.address_line_1, address_line_2: site.address_line_2, city: site.city, region: site.region, postal_code: site.postal_code, country_code: site.country_code, timezone: site.timezone, phone: site.phone,
  } : emptySite)
  const submit = (event: FormEvent) => { event.preventDefault(); void onSave(input) }
  return (
    <section className="content-section site-form-section" aria-labelledby="site-form-heading">
      <div className="section-heading"><h2 id="site-form-heading">{site ? `Edit ${site.name}` : 'Add site'}</h2></div>
      <form className="site-form" onSubmit={submit}>
        <label>Site name<input autoFocus required maxLength={240} value={input.name} onChange={(event) => setInput({ ...input, name: event.target.value })} /></label>
        <label>Code <span>Optional operator identifier</span><input maxLength={64} value={input.code} onChange={(event) => setInput({ ...input, code: event.target.value })} /></label>
        <label className="site-form-wide">Address<input maxLength={240} value={input.address_line_1} onChange={(event) => setInput({ ...input, address_line_1: event.target.value })} /></label>
        <label className="site-form-wide">Address line 2 <span>Optional</span><input maxLength={240} value={input.address_line_2} onChange={(event) => setInput({ ...input, address_line_2: event.target.value })} /></label>
        <label>City<input maxLength={120} value={input.city} onChange={(event) => setInput({ ...input, city: event.target.value })} /></label>
        <label>State or region<input maxLength={120} value={input.region} onChange={(event) => setInput({ ...input, region: event.target.value })} /></label>
        <label>Postal code<input maxLength={32} value={input.postal_code} onChange={(event) => setInput({ ...input, postal_code: event.target.value })} /></label>
        <label>Country code <span>Two letters</span><input maxLength={2} pattern="[A-Za-z]{2}" value={input.country_code} onChange={(event) => setInput({ ...input, country_code: event.target.value.toUpperCase() })} /></label>
        <label>Timezone <span>IANA name, such as America/Chicago</span><input maxLength={64} value={input.timezone} onChange={(event) => setInput({ ...input, timezone: event.target.value })} /></label>
        <label>Site phone <span>Optional</span><input type="tel" maxLength={64} value={input.phone} onChange={(event) => setInput({ ...input, phone: event.target.value })} /></label>
        <div className="form-actions"><button className="primary-button" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save site'}</button><button className="secondary-button" type="button" disabled={saving} onClick={onCancel}>Cancel</button></div>
      </form>
    </section>
  )
}

function LocationForm({ site, location, saving, onCancel, onSave }: { site: SiteRecord; location: LocationRecord | null; saving: boolean; onCancel: () => void; onSave: (input: LocationInput) => Promise<void> }) {
  const [input, setInput] = useState<LocationInput>(() => location ? { name: location.name, kind: location.kind, code: location.code, parent_id: location.parent_id } : { name: '', kind: 'room', code: '', parent_id: null })
  const submit = (event: FormEvent) => { event.preventDefault(); void onSave(input) }
  return (
    <form className="location-form" onSubmit={submit} aria-label={location ? `Edit ${location.name}` : `Add location to ${site.name}`}>
      <label>Name<input autoFocus required maxLength={240} value={input.name} onChange={(event) => setInput({ ...input, name: event.target.value })} /></label>
      <label>Type<select value={input.kind} onChange={(event) => setInput({ ...input, kind: event.target.value as LocationKind })}>{Object.entries(kindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>Parent<select value={input.parent_id ?? ''} onChange={(event) => setInput({ ...input, parent_id: event.target.value || null })}><option value="">Top level</option>{site.locations.filter((item) => item.id !== location?.id).map((item) => <option key={item.id} value={item.id}>{item.name} ({kindLabels[item.kind]})</option>)}</select></label>
      <label>Code <span>Optional</span><input maxLength={64} value={input.code} onChange={(event) => setInput({ ...input, code: event.target.value })} /></label>
      <div className="form-actions"><button className="primary-button" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save location'}</button><button className="secondary-button" type="button" disabled={saving} onClick={onCancel}>Cancel</button></div>
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
  const workspaceName = workspace?.name ?? 'the MSP'
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
        .catch((loadError: unknown) => { if (!controller.signal.aborted) { setPhase('error'); setError(errorMessage(loadError, 'Sites could not be loaded.')) } })
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
      refresh(editingSite === 'new' ? 'Site added.' : 'Site updated.')
    } catch (saveError) { setError(errorMessage(saveError, 'The site could not be saved.')) } finally { setSaving(false) }
  }
  const saveLocation = async (input: LocationInput) => {
    if (!editingLocation) return
    setSaving(true); setError(null); setMessage(null)
    try {
      if (editingLocation.location) await client.updateLocation(scope, editingLocation.site.id, editingLocation.location.id, input)
      else await client.createLocation(scope, editingLocation.site.id, input)
      refresh(editingLocation.location ? 'Location updated.' : 'Location added.')
    } catch (saveError) { setError(errorMessage(saveError, 'The location could not be saved.')) } finally { setSaving(false) }
  }
  const archive = async () => {
    if (!archiving) return
    setSaving(true); setError(null); setMessage(null)
    try {
      if (archiving.location) await client.archiveLocation(scope, archiving.site.id, archiving.location.id)
      else await client.archive(scope, archiving.site.id)
      refresh(archiving.location ? 'Location archived with its nested locations.' : 'Site archived with its locations.')
    } catch (archiveError) { setError(errorMessage(archiveError, 'The record could not be archived.')) } finally { setSaving(false) }
  }

  return (
    <>
      <header className="page-header"><div><h1>Sites</h1></div><button className="primary-button" type="button" aria-label={translate('sites.new')} title={translate('sites.new')} onClick={() => { setEditingSite('new'); setEditingLocation(null); setArchiving(null); setCustomFieldTarget(null); setMessage(null) }}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('sites.new')}</span></button></header>
      {error && <div className="form-error people-error" role="alert">{error}</div>}
      {message && <div className="form-success" role="status">{message}</div>}
      {editingSite && <SiteForm key={editingSite === 'new' ? 'new' : editingSite.id} site={editingSite === 'new' ? null : editingSite} saving={saving} onCancel={() => setEditingSite(null)} onSave={saveSite} />}
      {customFieldTarget && <EntityCustomFields workspace={workspace} entityId={customFieldTarget.id} entityName={customFieldTarget.name} onClose={() => setCustomFieldTarget(null)} client={customFieldsClient} />}
      <section className="content-section site-list-section" aria-labelledby="site-list-heading">
        <div className="section-heading site-list-heading"><h2 id="site-list-heading">Locations</h2><span>{result ? `${result.count} ${result.count === 1 ? 'site' : 'sites'}` : 'Loading'}</span></div>
        <label className="site-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search sites and locations</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search sites and locations" /></label>
        {visiblePhase === 'loading' && <p className="people-state" role="status">Loading sites…</p>}
        {visiblePhase === 'error' && <p className="people-state">Sites are unavailable.</p>}
        {visiblePhase === 'ready' && result?.results.length === 0 && <p className="people-state">{query ? 'No sites or locations match this search.' : `No sites have been added to ${workspaceName}.`}</p>}
        {visiblePhase === 'ready' && result && result.results.length > 0 && <div className="site-list">{result.results.map((site) => (
          <article className="site-row" key={site.id}>
            <div className="site-row-heading"><div><h3><MapPin size={16} aria-hidden="true" />{site.name}</h3><p>{address(site) || 'No address recorded'}{site.code ? ` · ${site.code}` : ''}</p></div><div className="site-actions"><button className="row-action" type="button" aria-label={`Add location to ${site.name}`} onClick={() => { setEditingLocation({ site, location: null }); setEditingSite(null); setArchiving(null); setCustomFieldTarget(null) }}><Plus size={15} />Location</button><button className="row-action" type="button" aria-label={`Custom fields for site ${site.name}`} onClick={() => { setCustomFieldTarget({ id: site.id, name: site.name }); setEditingSite(null); setEditingLocation(null); setArchiving(null) }}><ListPlus size={15} />Fields</button><button className="row-action" type="button" aria-label={`Edit site ${site.name}`} onClick={() => { setEditingSite(site); setEditingLocation(null); setArchiving(null); setCustomFieldTarget(null) }}><Pencil size={15} />Edit</button><button className="row-action danger" type="button" aria-label={`Archive site ${site.name}`} onClick={() => { setArchiving({ site }); setEditingSite(null); setEditingLocation(null); setCustomFieldTarget(null) }}><Trash2 size={15} />Archive</button></div></div>
            {editingLocation?.site.id === site.id && <LocationForm key={editingLocation.location?.id ?? 'new'} site={site} location={editingLocation.location} saving={saving} onCancel={() => setEditingLocation(null)} onSave={saveLocation} />}
            {site.locations.length === 0 ? <p className="location-empty">No nested locations.</p> : <ul className="location-tree">{locationRows(site.locations).map(({ location, depth }) => <li key={location.id} style={{ paddingLeft: 10 + depth * 22 }}><span><strong>{location.name}</strong><span>{kindLabels[location.kind]}{location.code ? ` · ${location.code}` : ''}</span></span><span className="site-actions"><button className="row-action" type="button" aria-label={`Custom fields for location ${location.name}`} onClick={() => { setCustomFieldTarget({ id: location.id, name: location.name }); setEditingSite(null); setEditingLocation(null); setArchiving(null) }}><ListPlus size={14} />Fields</button><button className="row-action" type="button" aria-label={`Edit location ${location.name}`} onClick={() => { setEditingLocation({ site, location }); setEditingSite(null); setArchiving(null); setCustomFieldTarget(null) }}><Pencil size={14} />Edit</button><button className="row-action danger" type="button" aria-label={`Archive location ${location.name}`} onClick={() => { setArchiving({ site, location }); setEditingSite(null); setEditingLocation(null); setCustomFieldTarget(null) }}><Trash2 size={14} />Archive</button></span></li>)}</ul>}
          </article>
        ))}</div>}
        {archiving && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-place-heading"><div><strong id="archive-place-heading">Archive {archiving.location?.name ?? archiving.site.name}?</strong><p>Nested locations are archived too. Existing People records retain their readable placement labels.</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? 'Archiving…' : 'Archive'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setArchiving(null)}>Cancel</button></div></div>}
      </section>
    </>
  )
}
