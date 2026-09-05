import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router'
import { MailPlus, RefreshCw, Search, ShieldCheck, UserRoundCheck } from 'lucide-react'
import { CollectionPagination } from '../CollectionPagination'
import { FilterMenu } from '../FilterMenu'
import { formatDateTime, translate } from '../i18n/localization'
import { AuthRequestError } from '../auth/api'
import type { Member } from '../access-control/api'
import type { StaffAdministrationClient, StaffInvitation } from './api'

type PendingAction = { kind: 'resend' | 'revoke'; invitation: StaffInvitation }
type Filter = 'all' | 'pending' | 'accepted' | 'expired' | 'revoked' | 'delivery_failed'
const PAGE_SIZE = 25

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
        <button className="secondary-button refresh-button" type="button" disabled={working} onClick={() => { setError(null); void reload().catch((loadError: unknown) => setError(message(loadError))) }}><RefreshCw size={15} />{translate('common.refresh')}</button>
      </div>

      {error && <div className="form-error settings-error" role="alert">{error}</div>}
      {notice && <div className="settings-success" role="status">{notice}</div>}

      <section className="access-section" aria-labelledby="invite-staff-heading">
        <div className="section-heading"><div><h2 id="invite-staff-heading">{translate('staff.inviteHeading')}</h2><p>{translate('staff.inviteHelp')}</p></div></div>
        <form className="staff-invitation-form" onSubmit={(event) => { void issue(event) }}>
          <label><span>{translate('auth.emailAddress')}</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" maxLength={254} required /></label>
          <button className="primary-button" type="submit" disabled={working || !email.trim()}><MailPlus size={16} />{working ? translate('staff.sending') : translate('staff.sendInvitation')}</button>
        </form>
      </section>

      <section className="access-section" aria-labelledby="msp-members-heading">
        <div className="section-heading"><div><h2 id="msp-members-heading">{translate('staff.membersHeading')}</h2><p>{translate('staff.membersHelp')}</p></div><Link className="secondary-button" to="/access-control"><ShieldCheck size={15} />{translate('staff.openAccessControl')}</Link></div>
        {members === null ? <p role="status" className="settings-state">{translate('staff.loadingMembers')}</p> : members.length === 0 ? <p className="settings-state">{translate('staff.noMembers')}</p> : <div className="staff-member-list" role="table" aria-label={translate('staff.membersHeading')}>
          <div className="staff-member-row header" role="row"><span role="columnheader">{translate('staff.member')}</span><span role="columnheader">{translate('staff.role')}</span><span role="columnheader">{translate('staff.joined')}</span></div>
          {members.map((member) => <div className="staff-member-row" role="row" key={member.id}><span role="cell"><UserRoundCheck size={16} /><span><strong>{member.display_name}</strong><small>{member.email}</small></span></span><span role="cell">{member.role.replaceAll('_', ' ')}</span><span role="cell">{member.joined_at ? <time dateTime={member.joined_at}>{formatDateTime(member.joined_at)}</time> : translate('staff.owner')}</span></div>)}
        </div>}
      </section>

      <section className="access-section" aria-labelledby="invitation-history-heading">
        <div className="section-heading"><div><h2 id="invitation-history-heading">{translate('staff.historyHeading')}</h2><p>{translate('staff.historyHelp')}</p></div></div>
        <div className="staff-invitation-filters">
          <label><span className="sr-only">{translate('staff.searchInvitation')}</span><Search size={15} /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1) }} placeholder={translate('staff.searchEmail')} /></label>
          <FilterMenu groups={[{ kind: 'choices', label: translate('staff.status'), value: filter, choices: [{ value: 'all', label: translate('staff.allStatuses') }, { value: 'pending', label: translate('staff.status.pending') }, { value: 'delivery_failed', label: translate('staff.status.delivery_failed') }, { value: 'accepted', label: translate('staff.status.accepted') }, { value: 'expired', label: translate('staff.status.expired') }, { value: 'revoked', label: translate('staff.status.revoked') }], onChange: (value) => { setFilter(value as Filter); setPage(1) } }]} activeCount={filter === 'all' ? 0 : 1} onClear={() => { setFilter('all'); setPage(1) }} menuLabel={translate('staff.filters')} />
        </div>
        {invitations === null ? <p role="status" className="settings-state">{translate('staff.loadingHistory')}</p> : filteredInvitations.length === 0 ? <p className="settings-state">{translate('staff.noMatchingInvitations')}</p> : <><div className="table-scroll" role="group" aria-label={translate('staff.invitationTable')} tabIndex={0}><table className="staff-invitation-table"><caption className="sr-only">{translate('staff.invitationTable')}</caption><thead><tr><th>{translate('staff.email')}</th><th>{translate('staff.status')}</th><th>{translate('staff.sent')}</th><th>{translate('staff.expires')}</th><th>{translate('staff.attempts')}</th><th><span className="sr-only">{translate('staff.actions')}</span></th></tr></thead><tbody>{invitationPage.map((invitation) => {
          const state = effectiveState(invitation)
          const actionable = invitation.state === 'pending' && state !== 'expired'
          return <tr key={invitation.id}><td><strong>{invitation.email}</strong><small>{translate('staff.initialRole')}</small></td><td><span className={`invitation-state ${state}`}>{stateLabel(invitation)}</span></td><td>{invitation.last_sent_at ? <time dateTime={invitation.last_sent_at}>{formatDateTime(invitation.last_sent_at)}</time> : translate('staff.notDelivered')}</td><td><time dateTime={invitation.expires_at}>{formatDateTime(invitation.expires_at)}</time></td><td>{invitation.delivery_attempts}</td><td>{actionable && <div className="table-actions"><button type="button" className="secondary-button" onClick={() => setPending({ kind: 'resend', invitation })}>{translate('staff.resend')}</button><button type="button" className="secondary-button danger-button" onClick={() => setPending({ kind: 'revoke', invitation })}>{translate('staff.revoke')}</button></div>}{state === 'expired' && <button type="button" className="secondary-button" onClick={() => { setEmail(invitation.email); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>{translate('staff.inviteAgain')}</button>}</td></tr>
        })}</tbody></table></div><CollectionPagination label={translate('staff.invitations')} page={page} pageSize={PAGE_SIZE} count={filteredInvitations.length} hasMore={page * PAGE_SIZE < filteredInvitations.length} onPageChange={setPage} /></>}
      </section>

      {pending && <div className="archive-confirmation" role="alertdialog" aria-labelledby="staff-invitation-confirmation-heading"><div><strong id="staff-invitation-confirmation-heading">{translate('staff.confirmInvitation')}</strong><p>{pending.kind === 'resend' ? translate('staff.confirmResend', { email: pending.invitation.email }) : translate('staff.confirmRevoke', { email: pending.invitation.email })}</p></div><div className="form-actions"><button className="primary-button" type="button" disabled={working} onClick={() => { void confirm() }}>{working ? translate('common.saving') : pending.kind === 'resend' ? translate('staff.sendReplacement') : translate('staff.revokeInvitation')}</button><button className="secondary-button" type="button" disabled={working} onClick={() => setPending(null)}>{translate('common.cancel')}</button></div></div>}
    </section>
  )
}
