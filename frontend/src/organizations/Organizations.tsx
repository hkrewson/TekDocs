import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { ExternalLink, Pencil, Trash2 } from 'lucide-react'
import { Link } from 'react-router'
import { browserOrganizationClient } from './api'
import type { Organization, OrganizationClassification, OrganizationClient, OrganizationInput } from './api'

const classificationLabels: Record<OrganizationClassification, string> = {
  client: 'Client',
  vendor: 'Vendor',
  manufacturer: 'Manufacturer',
  partner: 'Partner',
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
        <div><h2 id="organization-form-heading">{organization ? `Edit ${organization.name}` : 'Add organization'}</h2><p>Organizations may serve more than one business role.</p></div>
      </div>
      <form className="organization-form" onSubmit={submit}>
        <label>Display name<input autoFocus value={input.name} onChange={(event) => setInput({ ...input, name: event.target.value })} maxLength={240} required /></label>
        <label>Legal name <span>Optional</span><input value={input.legal_name} onChange={(event) => setInput({ ...input, legal_name: event.target.value })} maxLength={240} /></label>
        <label>Website <span>Optional</span><input type="url" placeholder="https://" value={input.website} onChange={(event) => setInput({ ...input, website: event.target.value })} maxLength={500} /></label>
        <fieldset>
          <legend>Classifications</legend>
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
          <button className="primary-button" type="submit" disabled={saving || input.classifications.length === 0}>{saving ? 'Saving…' : 'Save organization'}</button>
          <button className="secondary-button" type="button" disabled={saving} onClick={onCancel}>Cancel</button>
          {input.classifications.length === 0 && <span className="field-guidance" role="alert">Select at least one classification.</span>}
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
      .catch((loadError: unknown) => { if (active) setError(errorMessage(loadError, 'Organizations could not be loaded.')) })
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
      setMessage(editing === 'new' ? 'Organization added.' : 'Organization updated.')
    } catch (saveError) {
      setError(errorMessage(saveError, 'The organization could not be saved.'))
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
      setMessage('Organization archived.')
      setArchiving(null)
    } catch (archiveError) {
      setError(errorMessage(archiveError, 'The organization could not be archived.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <header className="page-header">
        <div><h1>Organizations</h1><p>Client, vendor, manufacturer, and partner records for this MSP.</p></div>
        <button className="primary-button" type="button" onClick={() => { setEditing('new'); setArchiving(null); setMessage(null) }}>New organization</button>
      </header>
      {error && <div className="form-error" role="alert">{error}</div>}
      {message && <div className="form-success" role="status">{message}</div>}
      {editing && <OrganizationForm key={editing === 'new' ? 'new' : editing.id} organization={editing === 'new' ? null : editing} saving={saving} onCancel={() => setEditing(null)} onSave={save} />}
      <section className="content-section organization-list-section" aria-labelledby="organization-list-heading">
        <div className="section-heading organization-list-heading">
          <h2 id="organization-list-heading">Organization records</h2>
          <label>Show<select value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)}><option value="all">All classifications</option>{classifications.map((classification) => <option key={classification} value={classification}>{classificationLabels[classification]}</option>)}</select></label>
        </div>
        {records === null && !error && <p className="organization-state" role="status">Loading organizations…</p>}
        {records !== null && visibleRecords.length === 0 && <p className="organization-state">{filter === 'all' ? 'No organizations have been added.' : `No ${classificationLabels[filter].toLowerCase()} organizations found.`}</p>}
        {visibleRecords.length > 0 && (
          <div className="organization-table" role="table" aria-label="Organizations">
            <div className="organization-table-header" role="row"><span role="columnheader">Name</span><span role="columnheader">Classifications</span><span role="columnheader">Website</span><span role="columnheader">Actions</span></div>
            {visibleRecords.map((organization) => (
              <div className="organization-table-row" role="row" key={organization.id}>
                <span role="cell"><Link className="organization-name-link" to={`/workspaces/organizations/${organization.id}/overview`}>{organization.name}</Link>{organization.legal_name && organization.legal_name !== organization.name && <span>{organization.legal_name}</span>}</span>
                <span role="cell">{organization.classifications.map((classification) => classificationLabels[classification]).join(', ')}</span>
                <span role="cell">{organization.website ? <a href={organization.website} target="_blank" rel="noreferrer">Visit site <ExternalLink size={13} aria-hidden="true" /></a> : '—'}</span>
                <span role="cell" className="organization-row-actions">
                  <button type="button" className="row-action" onClick={() => { setEditing(organization); setArchiving(null); setMessage(null) }}><Pencil size={15} aria-hidden="true" />Edit <span className="sr-only">{organization.name}</span></button>
                  <button type="button" className="row-action danger" onClick={() => { setArchiving(organization); setEditing(null); setMessage(null) }}><Trash2 size={15} aria-hidden="true" />Archive <span className="sr-only">{organization.name}</span></button>
                </span>
              </div>
            ))}
          </div>
        )}
        {archiving && (
          <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-confirmation-heading">
            <div><strong id="archive-confirmation-heading">Archive {archiving.name}?</strong><p>It will leave active organization lists. Recovery arrives with the recycle-bin workflow.</p></div>
            <div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? 'Archiving…' : 'Archive organization'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setArchiving(null)}>Cancel</button></div>
          </div>
        )}
      </section>
    </>
  )
}
