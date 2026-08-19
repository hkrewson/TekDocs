import { useEffect, useMemo, useState } from 'react'
import { translate } from '../i18n/localization'
import { AccessCollectionsPanel } from './AccessCollectionsPanel'
import type { AccessCatalog, AccessCollection, AccessControlClient, CustomRole, CustomRoleScope, Member, OrganizationAccess, ScopedRoleAssignment } from './api'

type RoleDraft = { name: string; description: string; scope: CustomRoleScope; permissions: string[] }
type Pending =
  | { kind: 'save-role'; draft: RoleDraft; role: CustomRole | null }
  | { kind: 'archive-role'; role: CustomRole }
  | { kind: 'assign'; member: Member; role: CustomRole; organization: OrganizationAccess | null; collection: AccessCollection | null }
  | { kind: 'remove-assignment'; assignment: ScopedRoleAssignment }

const emptyRole: RoleDraft = { name: '', description: '', scope: 'tenant', permissions: [] }

function messageFor(error: unknown) {
  return error instanceof Error ? error.message : 'Custom role administration is unavailable.'
}

export function CustomRolesPanel({ client, catalog, members, organizations }: {
  client: AccessControlClient
  catalog: AccessCatalog
  members: Member[]
  organizations: OrganizationAccess[]
}) {
  const [roles, setRoles] = useState<CustomRole[] | null>(null)
  const [assignments, setAssignments] = useState<ScopedRoleAssignment[] | null>(null)
  const [collections, setCollections] = useState<AccessCollection[] | null>(null)
  const [roleDraft, setRoleDraft] = useState<RoleDraft>(emptyRole)
  const [editingRole, setEditingRole] = useState<CustomRole | null>(null)
  const [memberId, setMemberId] = useState('')
  const [roleId, setRoleId] = useState('')
  const [organizationId, setOrganizationId] = useState('')
  const [collectionId, setCollectionId] = useState('')
  const [pending, setPending] = useState<Pending | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([client.customRoles(controller.signal), client.scopedAssignments(controller.signal), client.accessCollections(controller.signal)])
      .then(([loadedRoles, loadedAssignments, loadedCollections]) => {
        if (controller.signal.aborted) return
        setRoles(loadedRoles)
        setAssignments(loadedAssignments)
        setCollections(loadedCollections)
      })
      .catch((loadError: unknown) => { if (!controller.signal.aborted) setError(messageFor(loadError)) })
    return () => controller.abort()
  }, [client])

  const permissionGroups = useMemo(() => {
    const groups = new Map<string, typeof catalog.custom_assignable_permissions>()
    for (const permission of catalog.custom_assignable_permissions) {
      groups.set(permission.category, [...(groups.get(permission.category) ?? []), permission])
    }
    return [...groups.entries()]
  }, [catalog])
  const activeRoles = roles?.filter((role) => role.archived_at === null) ?? []
  const selectedRole = activeRoles.find((role) => role.id === roleId) ?? null
  const selectedMember = members.find((member) => member.id === memberId && !member.is_owner) ?? null
  const selectedOrganization = organizations.find((organization) => organization.id === organizationId) ?? null
  const selectedCollection = collections?.find((collection) => collection.id === collectionId && collection.archived_at === null) ?? null

  const resetRole = () => {
    setEditingRole(null)
    setRoleDraft(emptyRole)
  }

  const confirm = async () => {
    if (!pending) return
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      if (pending.kind === 'save-role') {
        const saved = pending.role
          ? await client.updateCustomRole(pending.role.id, {
              name: pending.draft.name,
              description: pending.draft.description,
              permissions: pending.draft.permissions,
            })
          : await client.createCustomRole(pending.draft)
        setRoles((current) => pending.role
          ? current?.map((role) => role.id === saved.id ? saved : role) ?? null
          : [...(current ?? []), saved])
        setMessage(`${saved.name} was ${pending.role ? 'updated' : 'created'}.`)
        resetRole()
      } else if (pending.kind === 'archive-role') {
        const archived = await client.archiveCustomRole(pending.role.id)
        setRoles((current) => current?.map((role) => role.id === archived.id ? archived : role) ?? null)
        setMessage(`${archived.name} was archived and no longer grants permissions.`)
      } else if (pending.kind === 'assign') {
        const assignmentWasPresent = assignments?.some((item) =>
          item.member_id === pending.member.id
          && item.role_id === pending.role.id
          && item.organization_id === (pending.organization?.id ?? null)
          && item.collection_id === (pending.collection?.id ?? null)) ?? false
        const assignment = await client.createScopedAssignment({
          user_id: pending.member.id,
          role_id: pending.role.id,
          organization_id: pending.organization?.id ?? null,
          collection_id: pending.collection?.id ?? null,
        })
        setAssignments((current) => current?.some((item) => item.id === assignment.id) ? current : [...(current ?? []), assignment])
        if (!assignmentWasPresent) {
          setRoles((current) => current?.map((role) => role.id === assignment.role_id ? { ...role, assignment_count: role.assignment_count + 1 } : role) ?? null)
        }
        setMessage(`${assignment.role_name} was assigned to ${assignment.member_name}.`)
        setMemberId('')
        setRoleId('')
        setOrganizationId('')
        setCollectionId('')
      } else {
        await client.removeScopedAssignment(pending.assignment.id)
        setAssignments((current) => current?.filter((item) => item.id !== pending.assignment.id) ?? null)
        setRoles((current) => current?.map((role) => role.id === pending.assignment.role_id ? { ...role, assignment_count: Math.max(0, role.assignment_count - 1) } : role) ?? null)
        setMessage(`${pending.assignment.role_name} was removed from ${pending.assignment.member_name}.`)
      }
      setPending(null)
    } catch (saveError) {
      setError(messageFor(saveError))
    } finally {
      setSaving(false)
    }
  }

  const validRole = roleDraft.name.trim().length > 0 && roleDraft.permissions.length > 0
  const duplicateAssignment = Boolean(selectedMember && selectedRole && assignments?.some((assignment) =>
    assignment.member_id === selectedMember.id
    && assignment.role_id === selectedRole.id
    && assignment.organization_id === (selectedRole.scope === 'organization' ? selectedOrganization?.id ?? null : null)
    && assignment.collection_id === (selectedRole.scope === 'collection' ? selectedCollection?.id ?? null : null)))
  const validAssignment = selectedMember && selectedRole
    && (selectedRole.scope === 'tenant' || (selectedRole.scope === 'organization' ? selectedOrganization : selectedCollection))
    && !duplicateAssignment

  return <section className="access-section" aria-labelledby="custom-roles-heading" aria-busy={roles === null || assignments === null || collections === null}>
    <div className="section-heading"><div><h2 id="custom-roles-heading">Custom roles</h2><p>Add operational permissions at MSP or exact-organization scope. These grants never bypass client staff assignments.</p></div></div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {message && <div className="form-success" role="status">{message}</div>}
    {(roles === null || assignments === null || collections === null) && !error && <p role="status">Loading custom roles…</p>}
    {roles !== null && assignments !== null && collections !== null && <>
      <AccessCollectionsPanel client={client} collections={collections} setCollections={setCollections} organizations={organizations} />
      <form className="custom-role-form" onSubmit={(event) => { event.preventDefault(); if (validRole) setPending({ kind: 'save-role', draft: roleDraft, role: editingRole }) }}>
        <label><span>Role name</span><input value={roleDraft.name} maxLength={80} required onChange={(event) => setRoleDraft((current) => ({ ...current, name: event.target.value }))} /></label>
        <label><span>Scope</span><select value={roleDraft.scope} disabled={editingRole !== null} onChange={(event) => setRoleDraft((current) => ({ ...current, scope: event.target.value as CustomRoleScope }))}><option value="tenant">MSP-wide</option><option value="organization">One organization</option><option value="collection">Organization collection</option></select></label>
        <label className="custom-role-description"><span>Description</span><input value={roleDraft.description} maxLength={500} onChange={(event) => setRoleDraft((current) => ({ ...current, description: event.target.value }))} /></label>
        <fieldset className="permission-picker"><legend>Permissions</legend>{permissionGroups.map(([category, permissions]) => <div key={category}><strong>{category}</strong>{permissions.map((permission) => <label key={permission.key}><input type="checkbox" checked={roleDraft.permissions.includes(permission.key)} onChange={(event) => setRoleDraft((current) => ({ ...current, permissions: event.target.checked ? [...current.permissions, permission.key] : current.permissions.filter((key) => key !== permission.key) }))} /><span>{permission.label}{permission.requires_mfa ? ' · MFA required' : ''}</span></label>)}</div>)}</fieldset>
        <div className="form-actions"><button className="primary-button" type="submit" disabled={!validRole}>Review {editingRole ? 'update' : 'role'}</button>{editingRole && <button className="secondary-button" type="button" onClick={resetRole}>{translate('accessControl.cancelEdit')}</button>}</div>
      </form>

      {roles.length === 0 ? <p className="settings-state">No custom roles have been defined.</p> : <div className="custom-role-list" role="table" aria-label="Custom roles">
        <div className="custom-role-row header" role="row"><span role="columnheader">Role</span><span role="columnheader">Scope</span><span role="columnheader">Permissions</span><span role="columnheader">Assignments</span><span role="columnheader">Actions</span></div>
        {roles.map((role) => <div className="custom-role-row" role="row" key={role.id}>
          <span role="cell"><strong>{role.name}</strong><span>{role.description || 'No description'}{role.archived_at ? ' · Archived' : ''}</span></span>
          <span role="cell">{role.scope === 'tenant' ? 'MSP-wide' : role.scope === 'organization' ? 'Organization' : 'Collection'}</span>
          <span role="cell">{role.permissions.length}</span><span role="cell">{role.assignment_count}</span>
          <span role="cell">{role.archived_at ? 'Retained for history' : <><button className="secondary-button" type="button" onClick={() => { setEditingRole(role); setRoleDraft({ name: role.name, description: role.description, scope: role.scope, permissions: role.permissions }) }}>{translate('common.edit')}</button><button className="secondary-button" type="button" onClick={() => setPending({ kind: 'archive-role', role })}>{translate('common.archive')}</button></>}</span>
        </div>)}
      </div>}

      <div className="section-heading custom-assignment-heading"><div><h3>Scoped assignments</h3><p>Assign an active custom role to an MSP member. Organization and collection roles need an exact target.</p></div></div>
      <form className="scoped-role-form" onSubmit={(event) => { event.preventDefault(); if (validAssignment && selectedMember && selectedRole) setPending({ kind: 'assign', member: selectedMember, role: selectedRole, organization: selectedOrganization, collection: selectedCollection }) }}>
        <label><span>MSP member</span><select aria-label="Custom role member" value={memberId} onChange={(event) => setMemberId(event.target.value)}><option value="">Select a member</option>{members.filter((member) => !member.is_owner).map((member) => <option value={member.id} key={member.id}>{member.display_name}</option>)}</select></label>
        <label><span>Custom role</span><select aria-label="Custom role definition" value={roleId} onChange={(event) => { setRoleId(event.target.value); setOrganizationId(''); setCollectionId('') }}><option value="">Select a role</option>{activeRoles.map((role) => <option value={role.id} key={role.id}>{role.name} · {role.scope === 'tenant' ? 'MSP-wide' : role.scope}</option>)}</select></label>
        {selectedRole?.scope === 'organization' && <label><span>Organization</span><select aria-label="Custom role organization" value={organizationId} onChange={(event) => setOrganizationId(event.target.value)}><option value="">Select an organization</option>{organizations.map((organization) => <option value={organization.id} key={organization.id}>{organization.name}</option>)}</select></label>}
        {selectedRole?.scope === 'collection' && <label><span>Collection</span><select aria-label="Custom role collection" value={collectionId} onChange={(event) => setCollectionId(event.target.value)}><option value="">Select a collection</option>{collections.filter((collection) => collection.archived_at === null).map((collection) => <option value={collection.id} key={collection.id}>{collection.name}</option>)}</select></label>}
        <button className="secondary-button" type="submit" disabled={!validAssignment}>{translate('accessControl.reviewCustomAssignment')}</button>
        {duplicateAssignment && <p className="form-error" role="status">This exact assignment already exists.</p>}
      </form>
      {assignments.length === 0 ? <p className="settings-state">No custom roles are assigned.</p> : <ul className="scoped-assignment-list">{assignments.map((assignment) => <li key={assignment.id}><span><strong>{assignment.member_name}</strong><span>{assignment.member_email}</span></span><span><strong>{assignment.role_name}</strong><span>{assignment.organization_name ?? assignment.collection_name ?? 'MSP-wide'}</span></span><button className="secondary-button" type="button" onClick={() => setPending({ kind: 'remove-assignment', assignment })}>{translate('common.remove')}</button></li>)}</ul>}
    </>}
    {pending && <div className="archive-confirmation" role="alertdialog" aria-labelledby="custom-role-confirmation-heading"><div><strong id="custom-role-confirmation-heading">Confirm custom role change</strong><p>{pending.kind === 'save-role' ? `${pending.role ? 'Update' : 'Create'} ${pending.draft.name}? ${pending.role ? `This immediately affects ${pending.role.assignment_count} assignment${pending.role.assignment_count === 1 ? '' : 's'}.` : 'It grants nothing until assigned.'}` : pending.kind === 'archive-role' ? `Archive ${pending.role.name}? Its ${pending.role.assignment_count} assignment${pending.role.assignment_count === 1 ? '' : 's'} will immediately stop granting permissions.` : pending.kind === 'assign' ? `Assign ${pending.role.name} to ${pending.member.display_name}${pending.organization ? ` only for ${pending.organization.name}` : pending.collection ? ` for organizations in ${pending.collection.name}` : ' across reachable workspaces'}?` : `Remove ${pending.assignment.role_name} from ${pending.assignment.member_name}?`}</p></div><div className="form-actions"><button className="primary-button" type="button" disabled={saving} onClick={() => { void confirm() }}>{saving ? 'Saving…' : 'Confirm change'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setPending(null)}>{translate('common.cancel')}</button></div></div>}
  </section>
}
