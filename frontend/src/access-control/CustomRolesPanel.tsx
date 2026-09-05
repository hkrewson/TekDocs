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
  return error instanceof Error ? error.message : translate('accessControl.customRolesUnavailable')
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
        setMessage(pending.role ? translate('accessControl.customRoleUpdated', { name: saved.name }) : translate('accessControl.customRoleCreated', { name: saved.name }))
        resetRole()
      } else if (pending.kind === 'archive-role') {
        const archived = await client.archiveCustomRole(pending.role.id)
        setRoles((current) => current?.map((role) => role.id === archived.id ? archived : role) ?? null)
        setMessage(translate('accessControl.customRoleArchived', { name: archived.name }))
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
        setMessage(translate('accessControl.customRoleAssigned', { role: assignment.role_name, member: assignment.member_name }))
        setMemberId('')
        setRoleId('')
        setOrganizationId('')
        setCollectionId('')
      } else {
        await client.removeScopedAssignment(pending.assignment.id)
        setAssignments((current) => current?.filter((item) => item.id !== pending.assignment.id) ?? null)
        setRoles((current) => current?.map((role) => role.id === pending.assignment.role_id ? { ...role, assignment_count: Math.max(0, role.assignment_count - 1) } : role) ?? null)
        setMessage(translate('accessControl.customRoleRemoved', { role: pending.assignment.role_name, member: pending.assignment.member_name }))
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
    <div className="section-heading"><div><h2 id="custom-roles-heading">{translate('accessControl.customRoles')}</h2><p>{translate('accessControl.customRolesHelp')}</p></div></div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {message && <div className="form-success" role="status">{message}</div>}
    {(roles === null || assignments === null || collections === null) && !error && <p role="status">{translate('accessControl.loadingCustomRoles')}</p>}
    {roles !== null && assignments !== null && collections !== null && <>
      <AccessCollectionsPanel client={client} collections={collections} setCollections={setCollections} organizations={organizations} />
      <form className="custom-role-form" onSubmit={(event) => { event.preventDefault(); if (validRole) setPending({ kind: 'save-role', draft: roleDraft, role: editingRole }) }}>
        <label><span>{translate('accessControl.roleName')}</span><input value={roleDraft.name} maxLength={80} required onChange={(event) => setRoleDraft((current) => ({ ...current, name: event.target.value }))} /></label>
        <label><span>{translate('accessControl.scope')}</span><select value={roleDraft.scope} disabled={editingRole !== null} onChange={(event) => setRoleDraft((current) => ({ ...current, scope: event.target.value as CustomRoleScope }))}><option value="tenant">{translate('accessControl.mspWide')}</option><option value="organization">{translate('accessControl.oneClient')}</option><option value="collection">{translate('accessControl.clientCollection')}</option></select></label>
        <label className="custom-role-description"><span>{translate('accessControl.description')}</span><input value={roleDraft.description} maxLength={500} onChange={(event) => setRoleDraft((current) => ({ ...current, description: event.target.value }))} /></label>
        <fieldset className="permission-picker"><legend>{translate('accessControl.permissions')}</legend>{permissionGroups.map(([category, permissions]) => <div key={category}><strong>{category}</strong>{permissions.map((permission) => <label key={permission.key}><input type="checkbox" checked={roleDraft.permissions.includes(permission.key)} onChange={(event) => setRoleDraft((current) => ({ ...current, permissions: event.target.checked ? [...current.permissions, permission.key] : current.permissions.filter((key) => key !== permission.key) }))} /><span>{permission.label}{permission.requires_mfa ? translate('accessControl.mfaRequiredSuffix') : ''}</span></label>)}</div>)}</fieldset>
        <div className="form-actions"><button className="primary-button" type="submit" disabled={!validRole}>{editingRole ? translate('accessControl.reviewUpdate') : translate('accessControl.reviewRole')}</button>{editingRole && <button className="secondary-button" type="button" onClick={resetRole}>{translate('accessControl.cancelEdit')}</button>}</div>
      </form>

      {roles.length === 0 ? <p className="settings-state">{translate('accessControl.noCustomRoles')}</p> : <div className="custom-role-list" role="table" aria-label={translate('accessControl.customRoles')}>
        <div className="custom-role-row header" role="row"><span role="columnheader">{translate('accessControl.role')}</span><span role="columnheader">{translate('accessControl.scope')}</span><span role="columnheader">{translate('accessControl.permissions')}</span><span role="columnheader">{translate('accessControl.assignments')}</span><span role="columnheader">{translate('accessControl.actions')}</span></div>
        {roles.map((role) => <div className="custom-role-row" role="row" key={role.id}>
          <span role="cell"><strong>{role.name}</strong><span>{role.description || translate('accessControl.noDescription')}{role.archived_at ? translate('accessControl.archivedSuffix') : ''}</span></span>
          <span role="cell">{role.scope === 'tenant' ? translate('accessControl.mspWide') : role.scope === 'organization' ? translate('accessControl.client') : translate('accessControl.collection')}</span>
          <span role="cell">{role.permissions.length}</span><span role="cell">{role.assignment_count}</span>
          <span role="cell">{role.archived_at ? translate('accessControl.retainedForHistory') : <><button className="secondary-button" type="button" onClick={() => { setEditingRole(role); setRoleDraft({ name: role.name, description: role.description, scope: role.scope, permissions: role.permissions }) }}>{translate('common.edit')}</button><button className="secondary-button" type="button" onClick={() => setPending({ kind: 'archive-role', role })}>{translate('common.archive')}</button></>}</span>
        </div>)}
      </div>}

      <div className="section-heading custom-assignment-heading"><div><h3>{translate('accessControl.customAssignments')}</h3><p>{translate('accessControl.customAssignmentsHelp')}</p></div></div>
      <form className="scoped-role-form" onSubmit={(event) => { event.preventDefault(); if (validAssignment && selectedMember && selectedRole) setPending({ kind: 'assign', member: selectedMember, role: selectedRole, organization: selectedOrganization, collection: selectedCollection }) }}>
        <label><span>{translate('accessControl.mspMember')}</span><select aria-label={translate('accessControl.customRoleMember')} value={memberId} onChange={(event) => setMemberId(event.target.value)}><option value="">{translate('accessControl.selectMember')}</option>{members.filter((member) => !member.is_owner).map((member) => <option value={member.id} key={member.id}>{member.display_name}</option>)}</select></label>
        <label><span>{translate('accessControl.customRole')}</span><select aria-label={translate('accessControl.customRoleDefinition')} value={roleId} onChange={(event) => { setRoleId(event.target.value); setOrganizationId(''); setCollectionId('') }}><option value="">{translate('accessControl.selectRole')}</option>{activeRoles.map((role) => <option value={role.id} key={role.id}>{role.name} · {role.scope === 'tenant' ? translate('accessControl.mspWide') : role.scope}</option>)}</select></label>
        {selectedRole?.scope === 'organization' && <label><span>{translate('accessControl.client')}</span><select aria-label={translate('accessControl.customRoleClient')} value={organizationId} onChange={(event) => setOrganizationId(event.target.value)}><option value="">{translate('accessControl.selectClient')}</option>{organizations.map((organization) => <option value={organization.id} key={organization.id}>{organization.name}</option>)}</select></label>}
        {selectedRole?.scope === 'collection' && <label><span>{translate('accessControl.collection')}</span><select aria-label={translate('accessControl.customRoleCollection')} value={collectionId} onChange={(event) => setCollectionId(event.target.value)}><option value="">{translate('accessControl.selectCollection')}</option>{collections.filter((collection) => collection.archived_at === null).map((collection) => <option value={collection.id} key={collection.id}>{collection.name}</option>)}</select></label>}
        <button className="secondary-button" type="submit" disabled={!validAssignment}>{translate('accessControl.reviewCustomAssignment')}</button>
        {duplicateAssignment && <p className="form-error" role="status">{translate('accessControl.duplicateAssignment')}</p>}
      </form>
      {assignments.length === 0 ? <p className="settings-state">{translate('accessControl.noCustomAssignments')}</p> : <ul className="scoped-assignment-list">{assignments.map((assignment) => <li key={assignment.id}><span><strong>{assignment.member_name}</strong><span>{assignment.member_email}</span></span><span><strong>{assignment.role_name}</strong><span>{assignment.organization_name ?? assignment.collection_name ?? translate('accessControl.mspWide')}</span></span><button className="secondary-button" type="button" onClick={() => setPending({ kind: 'remove-assignment', assignment })}>{translate('common.remove')}</button></li>)}</ul>}
    </>}
    {pending && <div className="archive-confirmation" role="alertdialog" aria-labelledby="custom-role-confirmation-heading"><div><strong id="custom-role-confirmation-heading">{translate('accessControl.confirmCustomRoleChange')}</strong><p>{pending.kind === 'save-role' ? pending.role ? translate('accessControl.confirmCustomRoleUpdate', { name: pending.draft.name, count: pending.role.assignment_count }) : translate('accessControl.confirmCustomRoleCreate', { name: pending.draft.name }) : pending.kind === 'archive-role' ? translate('accessControl.confirmCustomRoleArchive', { name: pending.role.name, count: pending.role.assignment_count }) : pending.kind === 'assign' ? pending.organization ? translate('accessControl.confirmCustomRoleClientAssignment', { role: pending.role.name, member: pending.member.display_name, target: pending.organization.name }) : pending.collection ? translate('accessControl.confirmCustomRoleCollectionAssignment', { role: pending.role.name, member: pending.member.display_name, target: pending.collection.name }) : translate('accessControl.confirmCustomRoleMspAssignment', { role: pending.role.name, member: pending.member.display_name }) : translate('accessControl.confirmCustomRoleRemoval', { role: pending.assignment.role_name, member: pending.assignment.member_name })}</p></div><div className="form-actions"><button className="primary-button" type="button" disabled={saving} onClick={() => { void confirm() }}>{saving ? translate('common.saving') : translate('accessControl.confirmChange')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setPending(null)}>{translate('common.cancel')}</button></div></div>}
  </section>
}
