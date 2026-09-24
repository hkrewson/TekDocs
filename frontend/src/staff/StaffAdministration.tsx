import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import { MailPlus, RefreshCw, Search, ShieldCheck, UserRoundCheck } from 'lucide-react'
import { CollectionPagination } from '../CollectionPagination'
import { FilterMenu } from '../FilterMenu'
import { formatDateTime, translate } from '../i18n/localization'
import { AuthRequestError } from '../auth/api'
import type { Member } from '../access-control/api'
import type { StaffAdministrationClient, StaffInvitation } from './api'
import { RecordSections } from '../records/RecordNavigation'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import '../administration.css'

type PendingAction = { kind: 'resend' | 'revoke'; invitation: StaffInvitation }
type Filter = 'all' | 'pending' | 'accepted' | 'expired' | 'revoked' | 'delivery_failed'
const pageSizes = [25, 50, 100] as const

function message(error: unknown): string {
  return error instanceof Error ? error.message : translate('staff.unavailable')
}

function effectiveState(invitation: StaffInvitation): Filter {
  if (invitation.state === 'pending' && new Date(invitation.expires_at).getTime() <= Date.now()) return 'expired'
  if (invitation.state === 'pending' && invitation.last_delivery_failed_at && !invitation.last_sent_at) return 'delivery_failed'
  return invitation.state
}

function stateLabel(invitation: StaffInvitation): string {
  const state = effectiveState(invitation)
  return translate(`staff.status.${state}` as 'staff.status.pending' | 'staff.status.accepted' | 'staff.status.expired' | 'staff.status.revoked' | 'staff.status.delivery_failed')
}

export function StaffAdministration({ client }: { client: StaffAdministrationClient }) {
  const [parameters, setParameters] = useSearchParams()
  const section = parameters.get('section') === 'members' ? 'members' : 'invitations'
  const query = parameters.get('q') ?? ''
  const filter = (['pending', 'accepted', 'expired', 'revoked', 'delivery_failed'].includes(parameters.get('status') ?? '') ? parameters.get('status') : 'all') as Filter
  const page = Math.max(1, Number(parameters.get('page')) || 1)
  const parsedPageSize = Number(parameters.get('page_size'))
  const pageSize = pageSizes.includes(parsedPageSize as typeof pageSizes[number]) ? parsedPageSize : 25
  const inviting = parameters.get('invite') === '1'
  const [members, setMembers] = useState<Member[] | null>(null)
  const [invitations, setInvitations] = useState<StaffInvitation[] | null>(null)
  const [email, setEmail] = useState('')
  const [pending, setPending] = useState<PendingAction | null>(null)
  const [working, setWorking] = useState(false)
  const [closingAfterSave, setClosingAfterSave] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const updateParameters = (patch: Record<string, string | number | null>) => {
    const next = new URLSearchParams(parameters)
    for (const [key, value] of Object.entries(patch)) {
      if (value === null || value === '') next.delete(key)
      else next.set(key, String(value))
    }
    setParameters(next)
  }
  const closeInvitation = () => updateParameters({ invite: null })
  useUnsavedChanges(inviting && Boolean(email.trim()) && !closingAfterSave, working && !closingAfterSave, () => setEmail(''), inviting && !closingAfterSave)
  useEffect(() => {
    if (!inviting) return
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = overflow }
  }, [inviting])

  const reload = async (signal?: AbortSignal) => {
    const [loadedMembers, loadedInvitations] = await Promise.all([client.members(signal), client.invitations(signal)])
    setMembers(loadedMembers)
    setInvitations(loadedInvitations)
  }

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([client.members(controller.signal), client.invitations(controller.signal)])
      .then(([loadedMembers, loadedInvitations]) => {
        if (controller.signal.aborted) return
        setMembers(loadedMembers)
        setInvitations(loadedInvitations)
      })
      .catch((loadError: unknown) => {
        if (!controller.signal.aborted) setError(message(loadError))
      })
    return () => controller.abort()
  }, [client])

  const filteredInvitations = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase()
    return (invitations ?? []).filter((invitation) => {
      const matchesFilter = filter === 'all' || effectiveState(invitation) === filter
      return matchesFilter && (!normalized || invitation.email.toLocaleLowerCase().includes(normalized))
    })
  }, [filter, invitations, query])
  const invitationPage = filteredInvitations.slice((page - 1) * pageSize, page * pageSize)

  const issue = async (event: FormEvent) => {
    event.preventDefault()
    const submittedEmail = email.trim()
    setError(null)
    setNotice(null)
    setWorking(true)
    try {
      const created = await client.issue(submittedEmail)
      setInvitations((current) => [created, ...(current ?? []).filter((item) => item.id !== created.id)])
      setEmail('')
      setClosingAfterSave(true)
      window.setTimeout(() => { closeInvitation(); setClosingAfterSave(false) }, 50)
      setNotice(translate('staff.invitationSent', { email: created.email }))
    } catch (issueError) {
      if (issueError instanceof AuthRequestError && issueError.status === 503) {
        try { await reload() } catch { /* retain the delivery-safe primary error */ }
      }
      setError(message(issueError))
    } finally {
      setWorking(false)
    }
  }

  const confirm = async () => {
    if (!pending) return
    setError(null)
    setNotice(null)
    setWorking(true)
    try {
      const updated = pending.kind === 'resend'
        ? await client.resend(pending.invitation.id)
        : await client.revoke(pending.invitation.id)
      setInvitations((current) => (current ?? []).map((item) => item.id === updated.id ? updated : item))
      setNotice(pending.kind === 'resend' ? translate('staff.replacementSent', { email: updated.email }) : translate('staff.invitationRevoked', { email: updated.email }))
      setPending(null)
    } catch (actionError) {
      if (actionError instanceof AuthRequestError && actionError.status === 503) {
        try { await reload() } catch { /* retain the delivery-safe primary error */ }
      }
      setError(message(actionError))
    } finally {
      setWorking(false)
    }
  }

  return (
    <section className="content-section staff-administration" aria-labelledby="staff-administration-heading">
      <div className="section-heading settings-heading">
        <div><h1 id="staff-administration-heading">{translate('staff.heading')}</h1><p>{translate('staff.headingHelp')}</p></div>
        <div className="page-header-actions">{section === 'invitations' && <button className="primary-button" type="button" onClick={() => { setClosingAfterSave(false); updateParameters({ invite: 1 }) }}><MailPlus size={16} />{translate('staff.inviteHeading')}</button>}<button className="secondary-button refresh-button" type="button" disabled={working} onClick={() => { setError(null); void reload().catch((loadError: unknown) => setError(message(loadError))) }}><RefreshCw size={15} />{translate('common.refresh')}</button></div>
      </div>
      <p className="administration-help">{translate('staff.sectionsHelp')}</p>
      <RecordSections sections={[{ id: 'invitations', label: translate('staff.historyHeading'), href: '/staff?section=invitations' }, { id: 'members', label: translate('staff.membersHeading'), href: '/staff?section=members' }]} current={section} />

      {error && <div className="form-error settings-error" role="alert">{error}</div>}
      {notice && <div className="settings-success" role="status">{notice}</div>}

      {section === 'members' && <section className="access-section administration-section" aria-labelledby="msp-members-heading">
        <div className="section-heading"><div><h2 id="msp-members-heading">{translate('staff.membersHeading')}</h2><p>{translate('staff.membersHelp')}</p></div><Link className="secondary-button" to="/access-control"><ShieldCheck size={15} />{translate('staff.openAccessControl')}</Link></div>
        {members === null ? <p role="status" className="settings-state">{translate('staff.loadingMembers')}</p> : members.length === 0 ? <p className="settings-state">{translate('staff.noMembers')}</p> : <div className="staff-member-list" role="table" aria-label={translate('staff.membersHeading')}>
          <div className="staff-member-row header" role="row"><span role="columnheader">{translate('staff.member')}</span><span role="columnheader">{translate('staff.role')}</span><span role="columnheader">{translate('staff.joined')}</span></div>
          {members.map((member) => <div className="staff-member-row" role="row" key={member.id}><span role="cell"><UserRoundCheck size={16} /><span><strong>{member.display_name}</strong><small>{member.email}</small></span></span><span role="cell">{member.role.replaceAll('_', ' ')}</span><span role="cell">{member.joined_at ? <time dateTime={member.joined_at}>{formatDateTime(member.joined_at)}</time> : translate('staff.owner')}</span></div>)}
        </div>}
      </section>}

      {section === 'invitations' && <section className="access-section administration-section" aria-labelledby="invitation-history-heading">
        <div className="section-heading"><div><h2 id="invitation-history-heading">{translate('staff.historyHeading')}</h2><p>{translate('staff.historyHelp')}</p></div></div>
        <div className="staff-invitation-filters">
          <label><span className="sr-only">{translate('staff.searchInvitation')}</span><Search size={15} /><input value={query} onChange={(event) => updateParameters({ q: event.target.value, page: 1 })} placeholder={translate('staff.searchEmail')} /></label>
          <div className="collection-control-group"><FilterMenu groups={[{ kind: 'choices', label: translate('staff.status'), value: filter, choices: [{ value: 'all', label: translate('staff.allStatuses') }, { value: 'pending', label: translate('staff.status.pending') }, { value: 'delivery_failed', label: translate('staff.status.delivery_failed') }, { value: 'accepted', label: translate('staff.status.accepted') }, { value: 'expired', label: translate('staff.status.expired') }, { value: 'revoked', label: translate('staff.status.revoked') }], onChange: (value) => updateParameters({ status: value === 'all' ? null : value, page: 1 }) }]} activeCount={filter === 'all' ? 0 : 1} onClear={() => updateParameters({ status: null, page: 1 })} menuLabel={translate('staff.filters')} /><label className="collection-page-size">{translate('collections.pageSize')}<select value={pageSize} onChange={(event) => updateParameters({ page_size: event.target.value, page: 1 })}>{pageSizes.map((size) => <option key={size}>{size}</option>)}</select></label></div>
        </div>
        {invitations === null ? <p role="status" className="settings-state">{translate('staff.loadingHistory')}</p> : filteredInvitations.length === 0 ? <p className="settings-state">{translate('staff.noMatchingInvitations')}</p> : <><ul className="staff-invitation-list" aria-label={translate('staff.invitationTable')}>{invitationPage.map((invitation) => {
          const state = effectiveState(invitation)
          const actionable = invitation.state === 'pending' && state !== 'expired'
          return <li key={invitation.id}><div className="staff-invitation-identity"><strong>{invitation.email}</strong><small>{translate('staff.initialRole')}</small></div><span className={`invitation-state ${state}`}>{stateLabel(invitation)}</span><dl><div><dt>{translate('staff.sent')}</dt><dd>{invitation.last_sent_at ? <time dateTime={invitation.last_sent_at}>{formatDateTime(invitation.last_sent_at)}</time> : translate('staff.notDelivered')}</dd></div><div><dt>{translate('staff.expires')}</dt><dd><time dateTime={invitation.expires_at}>{formatDateTime(invitation.expires_at)}</time></dd></div><div><dt>{translate('staff.attempts')}</dt><dd>{invitation.delivery_attempts}</dd></div></dl><div className="table-actions">{actionable && <><button type="button" className="secondary-button" onClick={() => setPending({ kind: 'resend', invitation })}>{translate('staff.resend')}</button><button type="button" className="secondary-button danger-button" onClick={() => setPending({ kind: 'revoke', invitation })}>{translate('staff.revoke')}</button></>}{state === 'expired' && <button type="button" className="secondary-button" onClick={() => { setClosingAfterSave(false); setEmail(invitation.email); updateParameters({ invite: 1 }) }}>{translate('staff.inviteAgain')}</button>}</div></li>
        })}</ul><CollectionPagination label={translate('staff.invitations')} page={page} pageSize={pageSize} count={filteredInvitations.length} hasMore={page * pageSize < filteredInvitations.length} onPageChange={(next) => updateParameters({ page: next })} /></>}
      </section>}

      {inviting && <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="invite-staff-heading"><form className="record-form" onSubmit={(event) => { void issue(event) }}><div className="section-heading"><div><h2 id="invite-staff-heading">{translate('staff.inviteHeading')}</h2><p>{translate('staff.inviteHelp')}</p></div></div><label><span>{translate('auth.emailAddress')}</span><input autoFocus type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" maxLength={254} required /></label><div className="form-actions"><button className="primary-button" type="submit" disabled={working || !email.trim()}><MailPlus size={16} />{working ? translate('staff.sending') : translate('staff.sendInvitation')}</button><button className="secondary-button" type="button" disabled={working} onClick={closeInvitation}>{translate('common.cancel')}</button></div></form></section>}

      {pending && <div className="archive-confirmation" role="alertdialog" aria-labelledby="staff-invitation-confirmation-heading"><div><strong id="staff-invitation-confirmation-heading">{translate('staff.confirmInvitation')}</strong><p>{pending.kind === 'resend' ? translate('staff.confirmResend', { email: pending.invitation.email }) : translate('staff.confirmRevoke', { email: pending.invitation.email })}</p></div><div className="form-actions"><button className="primary-button" type="button" disabled={working} onClick={() => { void confirm() }}>{working ? translate('common.saving') : pending.kind === 'resend' ? translate('staff.sendReplacement') : translate('staff.revokeInvitation')}</button><button className="secondary-button" type="button" disabled={working} onClick={() => setPending(null)}>{translate('common.cancel')}</button></div></div>}
    </section>
  )
}
