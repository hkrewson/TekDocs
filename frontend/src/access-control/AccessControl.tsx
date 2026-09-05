import { useEffect, useMemo, useState } from 'react'
import { translate } from '../i18n/localization'
import type { AccessCatalog, AccessControlClient, AssignedStaff, BuiltInRole, Member, OrganizationAccess, OrganizationAccessMode, TenantRole } from './api'
import { browserAccessControlClient } from './api'
import { CustomRolesPanel } from './CustomRolesPanel'

const tenantRoles: TenantRole[] = ['administrator', 'technician', 'contributor', 'read_only']

type PendingChange =
  | { kind: 'role'; member: Member; role: TenantRole }
  | { kind: 'access'; organization: OrganizationAccess; accessMode: OrganizationAccessMode }
  | { kind: 'assign'; organization: OrganizationAccess; member: Member }
  | { kind: 'remove'; organization: OrganizationAccess; member: AssignedStaff }

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : translate('accessControl.unavailable')
}

export function AccessControl({ client = browserAccessControlClient }: { client?: AccessControlClient }) {
  const [catalog, setCatalog] = useState<AccessCatalog | null>(null)
  const [members, setMembers] = useState<Member[] | null>(null)
  const [organizations, setOrganizations] = useState<OrganizationAccess[] | null>(null)
  const [selectedRoles, setSelectedRoles] = useState<Record<string, TenantRole>>({})
  const [selectedModes, setSelectedModes] = useState<Record<string, OrganizationAccessMode>>({})
  const [selectedStaff, setSelectedStaff] = useState<Record<string, string>>({})
  const [pending, setPending] = useState<PendingChange | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([client.catalog(controller.signal), client.members(controller.signal), client.organizations(controller.signal)])
      .then(([loadedCatalog, loadedMembers, loadedOrganizations]) => {
        if (controller.signal.aborted) return
        setCatalog(loadedCatalog)
        setMembers(loadedMembers)
        setOrganizations(loadedOrganizations)
        setSelectedRoles(Object.fromEntries(loadedMembers.filter((item) => !item.is_owner).map((item) => [item.id, item.role as TenantRole])))
        setSelectedModes(Object.fromEntries(loadedOrganizations.map((item) => [item.id, item.access_mode])))
      })
      .catch((loadError: unknown) => { if (!controller.signal.aborted) setError(errorMessage(loadError)) })
    return () => controller.abort()
  }, [client])

  const roleByValue = useMemo(() => new Map(catalog?.roles.map((role) => [role.value, role]) ?? []), [catalog])
  const confirm = async () => {
    if (!pending) return
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      if (pending.kind === 'role') {
        const updated = await client.assignRole(pending.member.id, pending.role)
        setMembers((current) => current?.map((item) => item.id === updated.id ? updated : item) ?? null)
        setMessage(translate('accessControl.roleUpdated', { name: updated.display_name }))
      } else if (pending.kind === 'access') {
        const updated = await client.changeAccessMode(pending.organization.id, pending.accessMode)
        setOrganizations((current) => current?.map((item) => item.id === updated.id ? updated : item) ?? null)
        setMessage(translate('accessControl.clientAccessUpdated', { name: updated.name }))
      } else if (pending.kind === 'assign') {
        const updated = await client.assignStaff(pending.organization.id, pending.member.id)
        setOrganizations((current) => current?.map((item) => item.id === updated.id ? updated : item) ?? null)
        setSelectedStaff((current) => ({ ...current, [updated.id]: '' }))
        setMessage(translate('accessControl.staffAssigned', { member: pending.member.display_name, organization: updated.name }))
      } else {
        const updated = await client.removeStaff(pending.organization.id, pending.member.id)
        setOrganizations((current) => current?.map((item) => item.id === updated.id ? updated : item) ?? null)
        setMessage(translate('accessControl.staffRemoved', { member: pending.member.display_name, organization: updated.name }))
      }
      setPending(null)
    } catch (saveError) {
      setError(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  const loading = catalog === null || members === null || organizations === null
  return (
    <section className="content-section access-control-page" aria-labelledby="access-control-heading" aria-busy={loading}>
      <div className="section-heading"><div><h1 id="access-control-heading">{translate('accessControl.heading')}</h1><p>{translate('accessControl.headingHelp')}</p></div></div>
      {error && <div className="form-error" role="alert">{error}</div>}
      {message && <div className="form-success" role="status">{message}</div>}
      {loading && !error && <p role="status">{translate('accessControl.loading')}</p>}
      {!loading && (
        <>
          <section className="access-section" aria-labelledby="roles-heading">
            <div className="section-heading"><div><h2 id="roles-heading">{translate('accessControl.builtInRoles')}</h2><p>{translate('accessControl.builtInRolesHelp')}</p></div></div>
            <ul className="role-definitions">
              {catalog.roles.map((role) => <li key={role.value}><strong>{role.label}</strong><span>{role.description}</span><small>{role.assignable_scope === 'installation' ? translate('accessControl.ownerRole') : role.assignable_scope === 'tenant' ? translate('accessControl.mspWideRole') : translate('accessControl.clientRole')}</small></li>)}
            </ul>
          </section>
          <CustomRolesPanel client={client} catalog={catalog} members={members} organizations={organizations} />
          <section className="access-section" aria-labelledby="members-heading">
            <div className="section-heading"><div><h2 id="members-heading">{translate('accessControl.members')}</h2><p>{translate('accessControl.membersHelp')}</p></div></div>
            {members.length === 0 && <p>{translate('accessControl.noMembers')}</p>}
            {members.length > 0 && <div className="access-table" role="table" aria-label={translate('accessControl.members')}>
              <div className="access-row header" role="row"><span role="columnheader">{translate('accessControl.member')}</span><span role="columnheader">{translate('accessControl.role')}</span><span role="columnheader">{translate('accessControl.action')}</span></div>
              {members.map((member) => <div className="access-row" role="row" key={member.id}>
                <span role="cell"><strong>{member.display_name}</strong><span>{member.email}</span></span>
                <span role="cell">{member.is_owner
                  ? <span>{translate('accessControl.owner')}</span>
                  : <label><span className="sr-only">{translate('accessControl.roleFor', { name: member.display_name })}</span><select value={selectedRoles[member.id]} onChange={(event) => setSelectedRoles((current) => ({ ...current, [member.id]: event.target.value as TenantRole }))}>{tenantRoles.map((role) => <option key={role} value={role}>{roleByValue.get(role as BuiltInRole)?.label ?? role}</option>)}</select></label>}</span>
                <span role="cell">{member.is_owner
                  ? <span>{translate('accessControl.alwaysHasAccess')}</span>
                  : <button className="secondary-button" type="button" disabled={selectedRoles[member.id] === member.role} onClick={() => setPending({ kind: 'role', member, role: selectedRoles[member.id] })}>{translate('accessControl.reviewChange')}</button>}</span>
              </div>)}
            </div>}
          </section>
          <section className="access-section" aria-labelledby="organization-access-heading">
            <div className="section-heading"><div><h2 id="organization-access-heading">{translate('accessControl.clientAccess')}</h2><p>{translate('accessControl.clientAccessHelp')}</p></div></div>
            {organizations.length === 0 && <p>{translate('accessControl.noClients')}</p>}
            {organizations.length > 0 && <div className="access-table organization-access-table" role="table" aria-label={translate('accessControl.clientAccess')}>
              <div className="access-row header" role="row"><span role="columnheader">{translate('accessControl.client')}</span><span role="columnheader">{translate('accessControl.staffAccess')}</span><span role="columnheader">{translate('accessControl.action')}</span></div>
              {organizations.map((organization) => <div className="access-row" role="row" key={organization.id}>
                <span role="cell"><strong>{organization.name}</strong></span>
                <span role="cell"><label><span className="sr-only">{translate('accessControl.accessFor', { name: organization.name })}</span><select value={selectedModes[organization.id]} onChange={(event) => setSelectedModes((current) => ({ ...current, [organization.id]: event.target.value as OrganizationAccessMode }))}><option value="all_authorized">{translate('accessControl.allAllowedByRole')}</option><option value="assigned_only">{translate('accessControl.assignedOnly')}</option></select></label></span>
                <span role="cell"><button className="secondary-button" type="button" disabled={selectedModes[organization.id] === organization.access_mode} onClick={() => setPending({ kind: 'access', organization, accessMode: selectedModes[organization.id] })}>{translate('accessControl.reviewChange')}</button></span>
              </div>)}
            </div>}
          </section>
          <section className="access-section" aria-labelledby="staff-assignments-heading">
            <div className="section-heading"><div><h2 id="staff-assignments-heading">{translate('accessControl.assignments')}</h2><p>{translate('accessControl.assignmentsHelp')}</p></div></div>
            {organizations.length === 0 && <p>{translate('accessControl.noClients')}</p>}
            <div className="staff-assignment-list">
              {organizations.map((organization) => {
                const available = members.filter((member) => !member.is_owner && !organization.assigned_staff.some((item) => item.id === member.id))
                const selectedMember = members.find((member) => member.id === selectedStaff[organization.id])
                return <section key={organization.id} className="staff-assignment-group" aria-labelledby={`staff-${organization.id}`}>
                  <div><h3 id={`staff-${organization.id}`}>{organization.name}</h3><p>{organization.access_mode === 'assigned_only' ? translate('accessControl.restrictedToListed') : translate('accessControl.savedAssignments')}</p></div>
                  {organization.assigned_staff.length === 0
                    ? <p className="settings-state">{translate('accessControl.noAssignedStaff')}</p>
                    : <ul>{organization.assigned_staff.map((member) => <li key={member.id}><span><strong>{member.display_name}</strong><span>{member.email}</span></span><button className="secondary-button" type="button" onClick={() => setPending({ kind: 'remove', organization, member })}>{translate('common.remove')}</button></li>)}</ul>}
                  <div className="staff-assignment-form">
                    <label><span>{translate('accessControl.staffMember')}</span><select aria-label={translate('accessControl.staffFor', { name: organization.name })} value={selectedStaff[organization.id] ?? ''} onChange={(event) => setSelectedStaff((current) => ({ ...current, [organization.id]: event.target.value }))}><option value="">{translate('accessControl.selectMember')}</option>{available.map((member) => <option key={member.id} value={member.id}>{member.display_name} · {roleByValue.get(member.role)?.label ?? member.role}</option>)}</select></label>
                    <button className="secondary-button" type="button" disabled={!selectedMember} onClick={() => { if (selectedMember) setPending({ kind: 'assign', organization, member: selectedMember }) }}>{translate('accessControl.reviewAssignment')}</button>
                  </div>
                </section>
              })}
            </div>
          </section>
        </>
      )}
      {pending && <div className="archive-confirmation" role="alertdialog" aria-labelledby="access-change-heading">
        <div><strong id="access-change-heading">{translate('accessControl.confirmAccessChange')}</strong><p>{pending.kind === 'role'
          ? translate('accessControl.confirmRole', { name: pending.member.display_name, from: roleByValue.get(pending.member.role)?.label ?? pending.member.role, to: roleByValue.get(pending.role)?.label ?? pending.role })
          : pending.kind === 'access'
            ? pending.accessMode === 'assigned_only'
              ? translate('accessControl.confirmRestriction', { name: pending.organization.name })
              : translate('accessControl.confirmAllStaff', { name: pending.organization.name })
            : pending.kind === 'assign'
              ? translate('accessControl.confirmAssignment', { member: pending.member.display_name, organization: pending.organization.name })
              : translate('accessControl.confirmRemoval', { member: pending.member.display_name, organization: pending.organization.name })}</p></div>
        <div className="form-actions"><button className="primary-button" type="button" disabled={saving} onClick={() => { void confirm() }}>{saving ? translate('common.saving') : translate('accessControl.confirmChange')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setPending(null)}>{translate('common.cancel')}</button></div>
      </div>}
    </section>
  )
}
