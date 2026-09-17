import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ExternalLink, ListPlus, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { QuickDrawer } from '../collections/QuickDrawer'
import '../collections/collections.css'
import { EntityCustomFields } from '../custom-fields/EntityCustomFields'
import { browserCustomFieldsClient } from '../custom-fields/api'
import type { CustomFieldsClient } from '../custom-fields/api'
import { FilterMenu } from '../FilterMenu'
import { translate } from '../i18n/localization'
import { browserOrganizationClient } from './api'
import type { Organization, OrganizationClassification, OrganizationClient, OrganizationInput, OrganizationOrdering, OrganizationQuery } from './api'

const classificationLabels: Record<OrganizationClassification, string> = {
  client: translate('organizations.typeClient'),
  vendor: translate('organizations.typeVendor'),
  manufacturer: translate('organizations.typeManufacturer'),
  partner: translate('organizations.typePartner'),
}
const classifications = Object.keys(classificationLabels) as OrganizationClassification[]
const emptyInput: OrganizationInput = { name: '', legal_name: '', website: '', classifications: ['client'] }
const initialQuery: OrganizationQuery = { q: '', classification: '', ordering: 'name', page: 1, page_size: 25 }

function errorMessage(error: unknown, fallback: string) { return error instanceof Error ? error.message : fallback }
function inputFor(organization: Organization | null): OrganizationInput { return organization ? { name: organization.name, legal_name: organization.legal_name, website: organization.website, classifications: organization.classifications } : emptyInput }

function queryFromParams(parameters: URLSearchParams): OrganizationQuery {
  const classification = parameters.get('org_type') as OrganizationClassification | null
  const ordering = parameters.get('org_order') as OrganizationOrdering | null
  const page = Number(parameters.get('org_page'))
  return { ...initialQuery, q: parameters.get('q') ?? '', classification: classification && classifications.includes(classification) ? classification : '', ordering: ordering ?? 'name', page: Number.isInteger(page) && page > 0 ? page : 1 }
}

function OrganizationForm({ organization, saving, onCancel, onDirtyChange, onSave }: { organization: Organization | null; saving: boolean; onCancel: () => void; onDirtyChange: (dirty: boolean) => void; onSave: (input: OrganizationInput) => Promise<void> }) {
  const initial = useMemo(() => inputFor(organization), [organization])
  const [input, setInput] = useState<OrganizationInput>(initial)
  useEffect(() => { onDirtyChange(JSON.stringify(input) !== JSON.stringify(initial)); return () => onDirtyChange(false) }, [initial, input, onDirtyChange])
  const toggleClassification = (classification: OrganizationClassification) => setInput((current) => ({ ...current, classifications: current.classifications.includes(classification) ? current.classifications.filter((item) => item !== classification) : [...current.classifications, classification] }))
  const submit = (event: FormEvent) => { event.preventDefault(); void onSave(input) }
  return <form className="record-form record-form-grid organization-form record-form-wide operational-record-form" onSubmit={submit}>
    {!organization && <p className="site-form-wide field-guidance">{translate('organizations.newAccessHelp')}</p>}
    <label>{translate('organizations.displayName')}<input autoFocus value={input.name} onChange={(event) => setInput({ ...input, name: event.target.value })} maxLength={240} required /></label>
    <label>{translate('organizations.legalName')} <span>{translate('common.optional')}</span><input value={input.legal_name} onChange={(event) => setInput({ ...input, legal_name: event.target.value })} maxLength={240} /></label>
    <label className="site-form-wide">{translate('organizations.website')} <span>{translate('common.optional')}</span><input type="url" placeholder="https://" value={input.website} onChange={(event) => setInput({ ...input, website: event.target.value })} maxLength={500} /></label>
    <fieldset><legend>{translate('organizations.types')}</legend><div className="classification-options">{classifications.map((classification) => <label key={classification}><input type="checkbox" checked={input.classifications.includes(classification)} onChange={() => toggleClassification(classification)} />{classificationLabels[classification]}</label>)}</div></fieldset>
    <div className="form-actions"><button className="primary-button" type="submit" disabled={saving || input.classifications.length === 0}>{saving ? translate('common.saving') : translate('organizations.save')}</button><button className="secondary-button" type="button" disabled={saving} onClick={onCancel}>{translate('common.cancel')}</button>{input.classifications.length === 0 && <span className="field-guidance" role="alert">{translate('organizations.typeRequired')}</span>}</div>
  </form>
}

export function Organizations({ client = browserOrganizationClient, customFieldsClient = browserCustomFieldsClient }: { client?: OrganizationClient; customFieldsClient?: CustomFieldsClient }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState<OrganizationQuery>(() => queryFromParams(searchParams))
  const [result, setResult] = useState<Awaited<ReturnType<OrganizationClient['list']>> | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const drawerId = searchParams.get('organization')
  const [selected, setSelected] = useState<Organization | null>(null)
  const [drawerErrorId, setDrawerErrorId] = useState<string | null>(null)
  const [drawerMode, setDrawerMode] = useState<'view' | 'edit'>('view')
  const [customFieldsOpen, setCustomFieldsOpen] = useState(false)
  const [archiving, setArchiving] = useState<Organization | null>(null)
  const [dirty, setDirty] = useState(false)
  const [confirmingClose, setConfirmingClose] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)

  const updateDrawerUrl = useCallback((id: string | null, replace = false) => {
    const next = new URLSearchParams(searchParams)
    if (id) next.set('organization', id); else next.delete('organization')
    setSearchParams(next, { replace })
  }, [searchParams, setSearchParams])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.list(query, controller.signal).then((loaded) => { if (!controller.signal.aborted) { setResult(loaded); setPhase('ready'); setError(null) } }).catch((loadError: unknown) => { if (!controller.signal.aborted) { setPhase('error'); setError(errorMessage(loadError, translate('organizations.loadFailed'))) } })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, query, revision])

  const listed = drawerId && drawerId !== 'new' ? result?.results.find((record) => record.id === drawerId) : null
  const drawerRecord = selected?.id === drawerId ? selected : listed
  const drawerPhase = drawerErrorId === drawerId ? 'error' : drawerRecord || drawerId === 'new' ? 'ready' : 'loading'
  useEffect(() => {
    if (!drawerId || drawerId === 'new' || listed) return
    const controller = new AbortController()
    client.retrieve(drawerId, controller.signal).then((record) => { if (!controller.signal.aborted) { setSelected(record); setDrawerErrorId(null) } }).catch(() => { if (!controller.signal.aborted) setDrawerErrorId(drawerId) })
    return () => controller.abort()
  }, [client, drawerId, listed])

  const changeQuery = (changes: Partial<OrganizationQuery>) => {
    const nextQuery = { ...query, ...changes, page: changes.page ?? 1 }
    const nextParams = new URLSearchParams(searchParams)
    if (nextQuery.q) nextParams.set('q', nextQuery.q); else nextParams.delete('q')
    if (nextQuery.classification) nextParams.set('org_type', nextQuery.classification); else nextParams.delete('org_type')
    if (nextQuery.ordering !== 'name') nextParams.set('org_order', nextQuery.ordering); else nextParams.delete('org_order')
    if (nextQuery.page > 1) nextParams.set('org_page', String(nextQuery.page)); else nextParams.delete('org_page')
    setQuery(nextQuery); setSearchParams(nextParams, { replace: true })
  }
  const sort = (field: 'name' | 'legal_name') => changeQuery({ ordering: query.ordering === field ? `-${field}` : field })
  const sortIndicator = (field: string) => query.ordering === field ? <ArrowUp size={13} aria-hidden="true" /> : query.ordering === `-${field}` ? <ArrowDown size={13} aria-hidden="true" /> : null
  const openOrganization = (organization: Organization, mode: 'view' | 'edit' = 'view') => { setSelected(organization); setDrawerErrorId(null); setDrawerMode(mode); setCustomFieldsOpen(false); setArchiving(null); setError(null); setMessage(null); updateDrawerUrl(organization.id) }
  const finishClose = () => { setDirty(false); setConfirmingClose(false); setCustomFieldsOpen(false); setArchiving(null); setError(null); setDrawerMode('view'); updateDrawerUrl(null) }
  const closeDrawer = () => { if (saving) return; if (dirty) { setConfirmingClose(true); return } finishClose() }

  const save = async (input: OrganizationInput) => {
    setSaving(true); setError(null); setMessage(null)
    try {
      const creating = drawerId === 'new'
      const saved = creating ? await client.create(input) : await client.update(drawerId!, input)
      setSelected(saved); setDirty(false); setDrawerMode('view'); updateDrawerUrl(saved.id, creating); setMessage(creating ? translate('organizations.added', { name: saved.name }) : translate('organizations.updated', { name: saved.name })); setRevision((value) => value + 1)
    } catch (saveError) { setError(errorMessage(saveError, translate('organizations.saveFailed'))) } finally { setSaving(false) }
  }
  const archive = async () => {
    if (!archiving) return
    setSaving(true); setError(null); setMessage(null)
    try { await client.archive(archiving.id); setMessage(translate('organizations.archived', { name: archiving.name })); setArchiving(null); updateDrawerUrl(null); setRevision((value) => value + 1) }
    catch (archiveError) { setError(errorMessage(archiveError, translate('organizations.archiveFailed'))) } finally { setSaving(false) }
  }

  return <>
    <header className="page-header"><div><h1>{translate('organizations.heading')}</h1></div><button className="primary-button" type="button" aria-label={translate('organizations.new')} title={translate('organizations.new')} onClick={() => { setSelected(null); setDrawerMode('edit'); setCustomFieldsOpen(false); setArchiving(null); setError(null); setMessage(null); updateDrawerUrl('new') }}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('organizations.new')}</span></button></header>
    {error && !drawerId && <div className="form-error" role="alert">{error}</div>}{message && !drawerId && <div className="form-success" role="status">{message}</div>}
    {drawerId && <QuickDrawer title={drawerId === 'new' ? translate('organizations.add') : drawerRecord?.name ?? translate('organizations.record')} onClose={closeDrawer} returnFocusId={drawerId === 'new' ? undefined : `organization-row-${drawerId}`} returnHref="/organizations" returnLabel={translate('organizations.back')}>
      {error && <div className="form-error" role="alert">{error}</div>}{message && <div className="form-success" role="status">{message}</div>}
      {drawerPhase === 'loading' && <p className="people-state" role="status">{translate('organizations.recordLoading')}</p>}{drawerPhase === 'error' && <div className="form-error" role="alert">{translate('organizations.recordUnavailable')}</div>}
      {drawerPhase === 'ready' && (drawerId === 'new' || drawerRecord) && (drawerId === 'new' || drawerMode === 'edit') && <OrganizationForm key={drawerId} organization={drawerId === 'new' ? null : drawerRecord!} saving={saving} onCancel={drawerId === 'new' ? closeDrawer : () => { setDirty(false); setError(null); setDrawerMode('view') }} onDirtyChange={setDirty} onSave={save} />}
      {drawerPhase === 'ready' && drawerId !== 'new' && drawerRecord && drawerMode === 'view' && <div className="operational-record organization-record"><div className="operational-record-actions"><Link className="primary-button" to={`/workspaces/organizations/${drawerRecord.id}/overview`}>{translate('organizations.openWorkspace')}<ExternalLink size={15} aria-hidden="true" /></Link><button className="secondary-button" type="button" onClick={() => setDrawerMode('edit')}><Pencil size={15} aria-hidden="true" />{translate('organizations.editDetails')}</button><button className="secondary-button" type="button" onClick={() => setCustomFieldsOpen(true)}><ListPlus size={15} aria-hidden="true" />{translate('organizations.fields')}</button><button className="secondary-button danger" type="button" onClick={() => setArchiving(drawerRecord)}><Trash2 size={15} aria-hidden="true" />{translate('common.archive')}</button></div><dl className="record-facts"><div><dt>{translate('organizations.legalName')}</dt><dd>{drawerRecord.legal_name || '—'}</dd></div><div><dt>{translate('organizations.types')}</dt><dd>{drawerRecord.classifications.map((classification) => classificationLabels[classification]).join(', ')}</dd></div><div><dt>{translate('organizations.website')}</dt><dd>{drawerRecord.website ? <a href={drawerRecord.website} target="_blank" rel="noreferrer">{drawerRecord.website}<ExternalLink size={13} aria-hidden="true" /></a> : '—'}</dd></div><div><dt>{translate('organizations.access')}</dt><dd>{translate(drawerRecord.access_mode === 'all_authorized' ? 'organizations.accessTenantWide' : 'organizations.accessAssigned')}</dd></div></dl></div>}
      {customFieldsOpen && drawerRecord && <EntityCustomFields workspace={null} entityId={drawerRecord.id} entityName={drawerRecord.name} onClose={() => setCustomFieldsOpen(false)} client={customFieldsClient} />}
      {archiving && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-organization-heading"><div><strong id="archive-organization-heading">{translate('organizations.archiveQuestion', { name: archiving.name })}</strong><p>{translate('organizations.archiveHelp')}</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? translate('common.archiving') : translate('organizations.archiveButton')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setArchiving(null)}>{translate('common.cancel')}</button></div></div>}
      {confirmingClose && <div className="archive-confirmation" role="alertdialog" aria-labelledby="organization-unsaved-heading"><div><strong id="organization-unsaved-heading">{translate('navigation.unsaved.title')}</strong><p>{translate('navigation.unsaved.description')}</p></div><div className="form-actions"><button autoFocus className="primary-button" type="button" onClick={() => setConfirmingClose(false)}>{translate('navigation.unsaved.keep')}</button><button className="secondary-button" type="button" onClick={finishClose}>{translate('navigation.unsaved.discard')}</button></div></div>}
    </QuickDrawer>}
    <section className="content-section organization-list-section" aria-labelledby="organization-list-heading"><div className="section-heading organization-list-heading"><div><h2 id="organization-list-heading">{translate('organizations.list')}</h2><span>{result ? translate(result.count === 1 ? 'organizations.countOne' : 'organizations.countMany', { count: result.count }) : translate('common.loading')}</span></div><FilterMenu groups={[{ kind: 'choices', label: translate('organizations.showType'), value: query.classification || 'all', choices: [{ value: 'all', label: translate('organizations.allTypes') }, ...classifications.map((classification) => ({ value: classification, label: classificationLabels[classification] }))], onChange: (value) => changeQuery({ classification: value === 'all' ? '' : value as OrganizationClassification }) }]} activeCount={query.classification ? 1 : 0} onClear={() => changeQuery({ classification: '' })} menuLabel={translate('organizations.filters')} /></div>
      <label className="site-search"><Search size={16} aria-hidden="true" /><span className="sr-only">{translate('organizations.search')}</span><input type="search" aria-label={translate('organizations.search')} value={query.q} onChange={(event) => changeQuery({ q: event.target.value })} placeholder={translate('organizations.search')} /></label>
      {phase === 'loading' && <p className="organization-state" role="status">{translate('organizations.loading')}</p>}{phase === 'error' && <p className="organization-state">{translate('organizations.unavailable')}</p>}{phase === 'ready' && result?.results.length === 0 && <p className="organization-state">{query.q || query.classification ? translate('organizations.noMatch') : translate('organizations.empty')}</p>}
      {phase === 'ready' && result && result.results.length > 0 && <div className="people-table-wrap" role="group" aria-label={translate('organizations.table')} tabIndex={0}><table className="people-table organization-table"><thead><tr><th scope="col" aria-sort={query.ordering === 'name' ? 'ascending' : query.ordering === '-name' ? 'descending' : 'none'}><button type="button" onClick={() => sort('name')}>{translate('organizations.name')}{sortIndicator('name')}</button></th><th scope="col" aria-sort={query.ordering === 'legal_name' ? 'ascending' : query.ordering === '-legal_name' ? 'descending' : 'none'}><button type="button" onClick={() => sort('legal_name')}>{translate('organizations.legalName')}{sortIndicator('legal_name')}</button></th><th scope="col">{translate('organizations.types')}</th><th scope="col"><span className="sr-only">{translate('common.actions')}</span></th></tr></thead><tbody>{result.results.map((organization) => <tr key={organization.id}><td data-label={translate('organizations.name')}><button id={`organization-row-${organization.id}`} className="collection-name" type="button" onClick={() => openOrganization(organization)}>{organization.name}</button></td><td data-label={translate('organizations.legalName')}>{organization.legal_name || '—'}</td><td data-label={translate('organizations.types')}>{organization.classifications.map((classification) => classificationLabels[classification]).join(', ')}</td><td className="people-row-actions"><button className="row-action" type="button" aria-label={translate('organizations.edit', { name: organization.name })} onClick={() => openOrganization(organization, 'edit')}><Pencil size={15} aria-hidden="true" />{translate('common.edit')}</button></td></tr>)}</tbody></table></div>}
      {phase === 'ready' && result && result.count > result.page_size && <nav className="people-pagination" aria-label={translate('organizations.pages')}><button className="secondary-button" type="button" disabled={result.page === 1} onClick={() => changeQuery({ page: result.page - 1 })}><ChevronLeft size={15} aria-hidden="true" />{translate('common.previous')}</button><span>{translate('common.pageNumber', { page: result.page })}</span><button className="secondary-button" type="button" disabled={!result.has_more} onClick={() => changeQuery({ page: result.page + 1 })}>{translate('common.next')}<ChevronRight size={15} aria-hidden="true" /></button></nav>}
    </section>
  </>
}
