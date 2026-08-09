import { useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { AccessCollection, AccessCollectionInput, AccessControlClient, OrganizationAccess } from './api'

type Pending =
  | { kind: 'save'; collection: AccessCollection | null; draft: AccessCollectionInput }
  | { kind: 'archive'; collection: AccessCollection }

const emptyDraft: AccessCollectionInput = { name: '', description: '', organization_ids: [] }

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Access collection administration is unavailable.'
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
        setMessage(`${saved.name} was ${pending.collection ? 'updated' : 'created'}.`)
        reset()
      } else {
        const archived = await client.archiveAccessCollection(pending.collection.id)
        setCollections((current) => current?.map((collection) => collection.id === archived.id ? archived : collection) ?? null)
        setMessage(`${archived.name} was archived and no longer grants permissions.`)
      }
      setPending(null)
    } catch (saveError) {
      setError(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  return <section className="access-subsection" aria-labelledby="access-collections-heading">
    <div className="section-heading"><div><h3 id="access-collections-heading">Access collections</h3><p>Group organizations for reusable role scope. Collection membership never bypasses assigned-client access.</p></div></div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {message && <div className="form-success" role="status">{message}</div>}
    <form className="access-collection-form" onSubmit={(event) => { event.preventDefault(); if (draft.name.trim()) setPending({ kind: 'save', collection: editing, draft }) }}>
      <label><span>Collection name</span><input value={draft.name} maxLength={80} required onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} /></label>
      <label><span>Description</span><input value={draft.description} maxLength={500} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} /></label>
      <fieldset className="collection-organization-picker"><legend>Organizations</legend>{organizations.length === 0 ? <p>No organizations are available.</p> : organizations.map((organization) => <label key={organization.id}><input type="checkbox" checked={draft.organization_ids.includes(organization.id)} onChange={() => toggleOrganization(organization.id)} /><span>{organization.name}</span></label>)}</fieldset>
      <div className="form-actions"><button className="primary-button" type="submit" disabled={!draft.name.trim()}>Review {editing ? 'update' : 'collection'}</button>{editing && <button className="secondary-button" type="button" onClick={reset}>Cancel edit</button>}</div>
    </form>
    {collections.length === 0 ? <p className="settings-state">No access collections have been defined.</p> : <div className="access-collection-list" role="table" aria-label="Access collections">
      <div className="access-collection-row header" role="row"><span role="columnheader">Collection</span><span role="columnheader">Organizations</span><span role="columnheader">Assignments</span><span role="columnheader">Actions</span></div>
      {collections.map((collection) => <div className="access-collection-row" role="row" key={collection.id}>
        <span role="cell"><strong>{collection.name}</strong><span>{collection.description || 'No description'}{collection.archived_at ? ' · Archived' : ''}</span></span>
        <span role="cell">{collection.organizations.length ? collection.organizations.map((organization) => organization.name).join(', ') : 'No organizations'}</span>
        <span role="cell">{collection.assignment_count}</span>
        <span role="cell">{collection.archived_at ? 'Retained for history' : <><button className="secondary-button" type="button" onClick={() => { setEditing(collection); setDraft({ name: collection.name, description: collection.description, organization_ids: collection.organizations.map((organization) => organization.id) }) }}>Edit</button><button className="secondary-button" type="button" onClick={() => setPending({ kind: 'archive', collection })}>Archive</button></>}</span>
      </div>)}
    </div>}
    {pending && <div className="archive-confirmation" role="alertdialog" aria-labelledby="collection-confirmation-heading"><div><strong id="collection-confirmation-heading">Confirm access collection change</strong><p>{pending.kind === 'save' ? `${pending.collection ? 'Update' : 'Create'} ${pending.draft.name}? ${pending.collection ? `Membership changes immediately affect ${pending.collection.assignment_count} scoped assignment${pending.collection.assignment_count === 1 ? '' : 's'}.` : 'It grants nothing until a collection-scoped role is assigned.'}` : `Archive ${pending.collection.name}? Its ${pending.collection.assignment_count} scoped assignment${pending.collection.assignment_count === 1 ? '' : 's'} will immediately stop granting permissions.`}</p></div><div className="form-actions"><button className="primary-button" type="button" disabled={saving} onClick={() => { void confirm() }}>{saving ? 'Saving…' : 'Confirm change'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setPending(null)}>Cancel</button></div></div>}
  </section>
}
