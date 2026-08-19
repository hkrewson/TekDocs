import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router'
import { MailPlus, RefreshCw, Search, ShieldCheck, UserRoundCheck } from 'lucide-react'
import { CollectionPagination } from '../CollectionPagination'
import { formatDateTime, translate} from '../i18n/localization'
import { AuthRequestError } from '../auth/api'
import type { Member } from '../access-control/api'
import type { StaffAdministrationClient, StaffInvitation } from './api'

type PendingAction = { kind: 'resend' | 'revoke'; invitation: StaffInvitation }
type Filter = 'all' | 'pending' | 'accepted' | 'expired' | 'revoked' | 'delivery_failed'
const PAGE_SIZE = 25

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'Staff administration is unavailable.'
}

function effectiveState(invitation: StaffInvitation): Filter {
  if (invitation.state === 'pending' && new Date(invitation.expires_at).getTime() <= Date.now()) return 'expired'
  if (invitation.state === 'pending' && invitation.last_delivery_failed_at && !invitation.last_sent_at) return 'delivery_failed'
  return invitation.state
}

function stateLabel(invitation: StaffInvitation): string {
  const state = effectiveState(invitation)
  return state === 'delivery_failed' ? 'Delivery failed' : state.charAt(0).toUpperCase() + state.slice(1)
}

export function StaffAdministration({ client }: { client: StaffAdministrationClient }) {
  const [members, setMembers] = useState<Member[] | null>(null)
  const [invitations, setInvitations] = useState<StaffInvitation[] | null>(null)
  const [email, setEmail] = useState('')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [page, setPage] = useState(1)
  const [pending, setPending] = useState<PendingAction | null>(null)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

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
  const invitationPage = filteredInvitations.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

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
      setNotice(`Invitation sent to ${created.email}. The account will begin with Read-only access.`)
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
      setNotice(pending.kind === 'resend' ? `A replacement invitation was sent to ${updated.email}.` : `The invitation for ${updated.email} was revoked.`)
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
        <div><h1 id="staff-administration-heading">Staff &amp; invitations</h1><p>Invite MSP staff, review account activation, and hand accepted members into access control.</p></div>
        <button className="secondary-button refresh-button" type="button" disabled={working} onClick={() => { setError(null); void reload().catch((loadError: unknown) => setError(message(loadError))) }}><RefreshCw size={15} />{translate('common.refresh')}</button>
      </div>

      {error && <div className="form-error settings-error" role="alert">{error}</div>}
      {notice && <div className="settings-success" role="status">{notice}</div>}

      <section className="access-section" aria-labelledby="invite-staff-heading">
        <div className="section-heading"><div><h2 id="invite-staff-heading">Invite MSP staff</h2><p>Invitation links are delivered only by email. New members begin as Read-only until the owner reviews their role.</p></div></div>
        <form className="staff-invitation-form" onSubmit={(event) => { void issue(event) }}>
          <label><span>Email address</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" maxLength={254} required /></label>
          <button className="primary-button" type="submit" disabled={working || !email.trim()}><MailPlus size={16} />{working ? 'Sending…' : 'Send invitation'}</button>
        </form>
      </section>

      <section className="access-section" aria-labelledby="msp-members-heading">
        <div className="section-heading"><div><h2 id="msp-members-heading">MSP members</h2><p>Roles and client assignments are managed through the existing access-control policy boundary.</p></div><Link className="secondary-button" to="/access-control"><ShieldCheck size={15} />Open access control</Link></div>
        {members === null ? <p role="status" className="settings-state">Loading MSP members…</p> : members.length === 0 ? <p className="settings-state">No MSP members are available.</p> : <div className="staff-member-list" role="table" aria-label="MSP members">
          <div className="staff-member-row header" role="row"><span role="columnheader">Member</span><span role="columnheader">Role</span><span role="columnheader">Joined</span></div>
          {members.map((member) => <div className="staff-member-row" role="row" key={member.id}><span role="cell"><UserRoundCheck size={16} /><span><strong>{member.display_name}</strong><small>{member.email}</small></span></span><span role="cell">{member.role.replaceAll('_', ' ')}</span><span role="cell">{member.joined_at ? <time dateTime={member.joined_at}>{formatDateTime(member.joined_at)}</time> : 'Installation owner'}</span></div>)}
        </div>}
      </section>

      <section className="access-section" aria-labelledby="invitation-history-heading">
        <div className="section-heading"><div><h2 id="invitation-history-heading">Invitation history</h2><p>Up to 200 recent MSP-staff invitations are retained here. Client-portal invitations remain inside their client workflow.</p></div></div>
        <div className="staff-invitation-filters">
          <label><span className="sr-only">Search invitation email</span><Search size={15} /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1) }} placeholder="Search email" /></label>
          <label><span className="sr-only">Filter invitation status</span><select value={filter} onChange={(event) => { setFilter(event.target.value as Filter); setPage(1) }}><option value="all">All statuses</option><option value="pending">Pending</option><option value="delivery_failed">Delivery failed</option><option value="accepted">Accepted</option><option value="expired">Expired</option><option value="revoked">Revoked</option></select></label>
        </div>
        {invitations === null ? <p role="status" className="settings-state">Loading invitation history…</p> : filteredInvitations.length === 0 ? <p className="settings-state">No invitations match this view.</p> : <><div className="table-scroll" role="group" aria-label={translate('staff.invitationTable')} tabIndex={0}><table className="staff-invitation-table"><caption className="sr-only">MSP staff invitation history</caption><thead><tr><th>Email</th><th>Status</th><th>Sent</th><th>Expires</th><th>Attempts</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{invitationPage.map((invitation) => {
          const state = effectiveState(invitation)
          const actionable = invitation.state === 'pending' && state !== 'expired'
          return <tr key={invitation.id}><td><strong>{invitation.email}</strong><small>Initial role: Read-only</small></td><td><span className={`invitation-state ${state}`}>{stateLabel(invitation)}</span></td><td>{invitation.last_sent_at ? <time dateTime={invitation.last_sent_at}>{formatDateTime(invitation.last_sent_at)}</time> : 'Not delivered'}</td><td><time dateTime={invitation.expires_at}>{formatDateTime(invitation.expires_at)}</time></td><td>{invitation.delivery_attempts}</td><td>{actionable && <div className="table-actions"><button type="button" className="secondary-button" onClick={() => setPending({ kind: 'resend', invitation })}>{translate('staff.resend')}</button><button type="button" className="secondary-button danger-button" onClick={() => setPending({ kind: 'revoke', invitation })}>{translate('staff.revoke')}</button></div>}{state === 'expired' && <button type="button" className="secondary-button" onClick={() => { setEmail(invitation.email); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>{translate('staff.inviteAgain')}</button>}</td></tr>
        })}</tbody></table></div><CollectionPagination label="Staff invitations" page={page} pageSize={PAGE_SIZE} count={filteredInvitations.length} hasMore={page * PAGE_SIZE < filteredInvitations.length} onPageChange={setPage} /></>}
      </section>

      {pending && <div className="archive-confirmation" role="alertdialog" aria-labelledby="staff-invitation-confirmation-heading"><div><strong id="staff-invitation-confirmation-heading">Confirm invitation action</strong><p>{pending.kind === 'resend' ? `Send a replacement invitation to ${pending.invitation.email}? The prior link will stop working.` : `Revoke the invitation for ${pending.invitation.email}? Its link will stop working immediately.`}</p></div><div className="form-actions"><button className="primary-button" type="button" disabled={working} onClick={() => { void confirm() }}>{working ? 'Saving…' : pending.kind === 'resend' ? 'Send replacement' : 'Revoke invitation'}</button><button className="secondary-button" type="button" disabled={working} onClick={() => setPending(null)}>{translate('common.cancel')}</button></div></div>}
    </section>
  )
}
