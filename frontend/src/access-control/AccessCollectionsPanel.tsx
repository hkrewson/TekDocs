import { useState } from 'react'
import { translate } from '../i18n/localization'
import type { Dispatch, SetStateAction } from 'react'
import type { AccessCollection, AccessCollectionInput, AccessControlClient, OrganizationAccess } from './api'

type Pending =
  | { kind: 'save'; collection: AccessCollection | null; draft: AccessCollectionInput }
  | { kind: 'archive'; collection: AccessCollection }

const emptyDraft: AccessCollectionInput = { name: '', description: '', organization_ids: [] }

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : translate('accessControl.collectionsUnavailable')
}

export function AccessCollectionsPanel({ client, collections, setCollections, organizations }: {
  client: AccessControlClient
  collections: AccessCollection[]
  setCollections: Dispatch<SetStateAction<AccessCollection[] | null>>
  organizations: OrganizationAccess[]
}) {
  const [draft, setDraft] = useState<AccessCollectionInput>(emptyDraft)
  const [editing, setEditing] = useState<AccessCollection | null>(null)
  const [pending, setPending] = useState<Pending | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const reset = () => {
    setEditing(null)
    setDraft(emptyDraft)
  }

  const toggleOrganization = (organizationId: string) => {
    setDraft((current) => ({
      ...current,
      organization_ids: current.organization_ids.includes(organizationId)
        ? current.organization_ids.filter((id) => id !== organizationId)
        : [...current.organization_ids, organizationId],
    }))
  }

  const confirm = async () => {
    if (!pending) return
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      if (pending.kind === 'save') {
        const saved = pending.collection
          ? await client.updateAccessCollection(pending.collection.id, pending.draft)
          : await client.createAccessCollection(pending.draft)
        setCollections((current) => pending.collection
          ? current?.map((collection) => collection.id === saved.id ? saved : collection) ?? null
          : [...(current ?? []), saved])
        setMessage(pending.collection ? translate('accessControl.collectionUpdated', { name: saved.name }) : translate('accessControl.collectionCreated', { name: saved.name }))
        reset()
      } else {
        const archived = await client.archiveAccessCollection(pending.collection.id)
        setCollections((current) => current?.map((collection) => collection.id === archived.id ? archived : collection) ?? null)
        setMessage(translate('accessControl.collectionArchived', { name: archived.name }))
      }
      setPending(null)
    } catch (saveError) {
      setError(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  return <section className="access-subsection" aria-labelledby="access-collections-heading">
    <div className="section-heading"><div><h3 id="access-collections-heading">{translate('accessControl.clientCollections')}</h3><p>{translate('accessControl.clientCollectionsHelp')}</p></div></div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {message && <div className="form-success" role="status">{message}</div>}
    <form className="access-collection-form" onSubmit={(event) => { event.preventDefault(); if (draft.name.trim()) setPending({ kind: 'save', collection: editing, draft }) }}>
      <label><span>{translate('accessControl.collectionName')}</span><input value={draft.name} maxLength={80} required onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} /></label>
      <label><span>{translate('accessControl.description')}</span><input value={draft.description} maxLength={500} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} /></label>
      <fieldset className="collection-organization-picker"><legend>{translate('accessControl.clients')}</legend>{organizations.length === 0 ? <p>{translate('accessControl.noClients')}</p> : organizations.map((organization) => <label key={organization.id}><input type="checkbox" checked={draft.organization_ids.includes(organization.id)} onChange={() => toggleOrganization(organization.id)} /><span>{organization.name}</span></label>)}</fieldset>
      <div className="form-actions"><button className="primary-button" type="submit" disabled={!draft.name.trim()}>{editing ? translate('accessControl.reviewCollectionUpdate') : translate('accessControl.reviewCollection')}</button>{editing && <button className="secondary-button" type="button" onClick={reset}>{translate('accessControl.cancelEdit')}</button>}</div>
    </form>
    {collections.length === 0 ? <p className="settings-state">{translate('accessControl.noCollections')}</p> : <div className="access-collection-list" role="table" aria-label={translate('accessControl.clientCollections')}>
      <div className="access-collection-row header" role="row"><span role="columnheader">{translate('accessControl.collection')}</span><span role="columnheader">{translate('accessControl.clients')}</span><span role="columnheader">{translate('accessControl.assignments')}</span><span role="columnheader">{translate('accessControl.actions')}</span></div>
      {collections.map((collection) => <div className="access-collection-row" role="row" key={collection.id}>
        <span role="cell"><strong>{collection.name}</strong><span>{collection.description || translate('accessControl.noDescription')}{collection.archived_at ? translate('accessControl.archivedSuffix') : ''}</span></span>
        <span role="cell">{collection.organizations.length ? collection.organizations.map((organization) => organization.name).join(', ') : translate('accessControl.noClients')}</span>
        <span role="cell">{collection.assignment_count}</span>
        <span role="cell">{collection.archived_at ? translate('accessControl.retainedForHistory') : <><button className="secondary-button" type="button" onClick={() => { setEditing(collection); setDraft({ name: collection.name, description: collection.description, organization_ids: collection.organizations.map((organization) => organization.id) }) }}>{translate('common.edit')}</button><button className="secondary-button" type="button" onClick={() => setPending({ kind: 'archive', collection })}>{translate('common.archive')}</button></>}</span>
      </div>)}
    </div>}
    {pending && <div className="archive-confirmation" role="alertdialog" aria-labelledby="collection-confirmation-heading"><div><strong id="collection-confirmation-heading">{translate('accessControl.confirmCollectionChange')}</strong><p>{pending.kind === 'save' ? pending.collection ? translate('accessControl.confirmCollectionUpdate', { name: pending.draft.name, count: pending.collection.assignment_count }) : translate('accessControl.confirmCollectionCreate', { name: pending.draft.name }) : translate('accessControl.confirmCollectionArchive', { name: pending.collection.name, count: pending.collection.assignment_count })}</p></div><div className="form-actions"><button className="primary-button" type="button" disabled={saving} onClick={() => { void confirm() }}>{saving ? translate('common.saving') : translate('accessControl.confirmChange')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setPending(null)}>{translate('common.cancel')}</button></div></div>}
  </section>
}
