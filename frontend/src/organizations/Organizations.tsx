import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { ExternalLink, Pencil, Plus, Trash2 } from 'lucide-react'
import { translate } from '../i18n/localization'
import { Link } from 'react-router'
import { FilterMenu } from '../FilterMenu'
import { browserOrganizationClient } from './api'
import type { Organization, OrganizationClassification, OrganizationClient, OrganizationInput } from './api'

const classificationLabels: Record<OrganizationClassification, string> = {
  client: translate('organizations.typeClient'),
  vendor: translate('organizations.typeVendor'),
  manufacturer: translate('organizations.typeManufacturer'),
  partner: translate('organizations.typePartner'),
}
const classifications = Object.keys(classificationLabels) as OrganizationClassification[]
const emptyInput: OrganizationInput = { name: '', legal_name: '', website: '', classifications: ['client'] }

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

function OrganizationForm({ organization, saving, onCancel, onSave }: {
  organization: Organization | null
  saving: boolean
  onCancel: () => void
  onSave: (input: OrganizationInput) => Promise<void>
}) {
  const [input, setInput] = useState<OrganizationInput>(() => organization ? {
    name: organization.name,
    legal_name: organization.legal_name,
    website: organization.website,
    classifications: organization.classifications,
  } : emptyInput)

  const toggleClassification = (classification: OrganizationClassification) => {
    setInput((current) => ({
      ...current,
      classifications: current.classifications.includes(classification)
        ? current.classifications.filter((item) => item !== classification)
        : [...current.classifications, classification],
    }))
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    void onSave(input)
  }

  return (
    <section className="content-section organization-form-section" aria-labelledby="organization-form-heading">
      <div className="section-heading">
        <div><h2 id="organization-form-heading">{organization ? translate('organizations.edit', { name: organization.name }) : translate('organizations.add')}</h2>{!organization && <p>{translate('organizations.newAccessHelp')}</p>}</div>
      </div>
      <form className="organization-form" onSubmit={submit}>
        <label>{translate('organizations.displayName')}<input autoFocus value={input.name} onChange={(event) => setInput({ ...input, name: event.target.value })} maxLength={240} required /></label>
        <label>{translate('organizations.legalName')} <span>{translate('common.optional')}</span><input value={input.legal_name} onChange={(event) => setInput({ ...input, legal_name: event.target.value })} maxLength={240} /></label>
        <label>{translate('organizations.website')} <span>{translate('common.optional')}</span><input type="url" placeholder="https://" value={input.website} onChange={(event) => setInput({ ...input, website: event.target.value })} maxLength={500} /></label>
        <fieldset>
          <legend>{translate('organizations.types')}</legend>
          <div className="classification-options">
            {classifications.map((classification) => (
              <label key={classification}>
                <input type="checkbox" checked={input.classifications.includes(classification)} onChange={() => toggleClassification(classification)} />
                {classificationLabels[classification]}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="form-actions">
          <button className="primary-button" type="submit" disabled={saving || input.classifications.length === 0}>{saving ? translate('common.saving') : translate('organizations.save')}</button>
          <button className="secondary-button" type="button" disabled={saving} onClick={onCancel}>{translate('common.cancel')}</button>
          {input.classifications.length === 0 && <span className="field-guidance" role="alert">{translate('organizations.typeRequired')}</span>}
        </div>
      </form>
    </section>
  )
}

export function Organizations({ client = browserOrganizationClient }: { client?: OrganizationClient }) {
  const [records, setRecords] = useState<Organization[] | null>(null)
  const [filter, setFilter] = useState<OrganizationClassification | 'all'>('all')
  const [editing, setEditing] = useState<Organization | 'new' | null>(null)
  const [archiving, setArchiving] = useState<Organization | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    client.list()
      .then((loaded) => { if (active) setRecords(loaded) })
      .catch((loadError: unknown) => { if (active) setError(errorMessage(loadError, translate('organizations.loadFailed'))) })
    return () => { active = false }
  }, [client])

  const visibleRecords = useMemo(
    () => records?.filter((record) => filter === 'all' || record.classifications.includes(filter)) ?? [],
    [filter, records],
  )

  const save = async (input: OrganizationInput) => {
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const saved = editing === 'new' ? await client.create(input) : await client.update(editing!.id, input)
      setRecords((current) => [...(current ?? []).filter((record) => record.id !== saved.id), saved]
        .sort((left, right) => left.name.localeCompare(right.name)))
      setEditing(null)
      setMessage(editing === 'new' ? translate('organizations.added', { name: saved.name }) : translate('organizations.updated', { name: saved.name }))
    } catch (saveError) {
      setError(errorMessage(saveError, translate('organizations.saveFailed')))
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
      await client.archive(archiving.id)
      setRecords((current) => current?.filter((record) => record.id !== archiving.id) ?? [])
      setMessage(translate('organizations.archived', { name: archiving.name }))
      setArchiving(null)
    } catch (archiveError) {
      setError(errorMessage(archiveError, translate('organizations.archiveFailed')))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <header className="page-header">
        <div><h1>{translate('organizations.heading')}</h1></div>
        <button className="primary-button" type="button" aria-label={translate('organizations.new')} title={translate('organizations.new')} onClick={() => { setEditing('new'); setArchiving(null); setMessage(null) }}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('organizations.new')}</span></button>
      </header>
      {error && <div className="form-error" role="alert">{error}</div>}
      {message && <div className="form-success" role="status">{message}</div>}
      {editing && <OrganizationForm key={editing === 'new' ? 'new' : editing.id} organization={editing === 'new' ? null : editing} saving={saving} onCancel={() => setEditing(null)} onSave={save} />}
      <section className="content-section organization-list-section" aria-labelledby="organization-list-heading">
        <div className="section-heading organization-list-heading">
          <h2 id="organization-list-heading">{translate('organizations.list')}</h2>
          <FilterMenu groups={[{
            kind: 'choices',
            label: translate('organizations.showType'),
            value: filter,
            choices: [{ value: 'all', label: translate('organizations.allTypes') }, ...classifications.map((classification) => ({ value: classification, label: classificationLabels[classification] }))],
            onChange: (value) => setFilter(value as typeof filter),
          }]} activeCount={filter === 'all' ? 0 : 1} onClear={() => setFilter('all')} menuLabel={translate('organizations.filters')} />
        </div>
        {records === null && !error && <p className="organization-state" role="status">{translate('organizations.loading')}</p>}
        {records !== null && visibleRecords.length === 0 && <p className="organization-state">{filter === 'all' ? translate('organizations.empty') : translate('organizations.noTypeMatch', { type: classificationLabels[filter].toLowerCase() })}</p>}
        {visibleRecords.length > 0 && (
          <div className="organization-table" role="table" aria-label={translate('organizations.table')}>
            <div className="organization-table-header" role="row"><span role="columnheader">{translate('organizations.name')}</span><span role="columnheader">{translate('organizations.types')}</span><span role="columnheader">{translate('organizations.website')}</span><span role="columnheader">{translate('common.actions')}</span></div>
            {visibleRecords.map((organization) => (
              <div className="organization-table-row" role="row" key={organization.id}>
                <span role="cell"><Link className="organization-name-link" to={`/workspaces/organizations/${organization.id}/overview`}>{organization.name}</Link>{organization.legal_name && organization.legal_name !== organization.name && <span>{organization.legal_name}</span>}</span>
                <span role="cell" data-label={translate('organizations.types')}>{organization.classifications.map((classification) => classificationLabels[classification]).join(', ')}</span>
                <span role="cell" data-label={translate('organizations.website')}>{organization.website ? <a href={organization.website} target="_blank" rel="noreferrer">{translate('organizations.visitWebsite')} <ExternalLink size={13} aria-hidden="true" /></a> : '—'}</span>
                <span role="cell" className="organization-row-actions">
                  <button type="button" className="row-action" aria-label={translate('organizations.edit', { name: organization.name })} onClick={() => { setEditing(organization); setArchiving(null); setMessage(null) }}><Pencil size={15} aria-hidden="true" />{translate('common.edit')}</button>
                  <button type="button" className="row-action danger" aria-label={translate('organizations.archive', { name: organization.name })} onClick={() => { setArchiving(organization); setEditing(null); setMessage(null) }}><Trash2 size={15} aria-hidden="true" />{translate('common.archive')}</button>
                </span>
              </div>
            ))}
          </div>
        )}
        {archiving && (
          <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-confirmation-heading">
            <div><strong id="archive-confirmation-heading">{translate('organizations.archiveQuestion', { name: archiving.name })}</strong><p>{translate('organizations.archiveHelp')}</p></div>
            <div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? translate('common.archiving') : translate('organizations.archiveButton')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setArchiving(null)}>{translate('common.cancel')}</button></div>
          </div>
        )}
      </section>
    </>
  )
}
