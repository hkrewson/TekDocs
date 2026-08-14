import { AuthRequestError, browserCsrfToken, privilegedActionError } from '../auth/api'
import type { Member } from '../access-control/api'

export type InvitationState = 'pending' | 'expired' | 'revoked' | 'accepted'

export type StaffInvitation = {
  id: string
  email: string
  role: 'read_only'
  organization: null
  state: InvitationState
  expires_at: string
  last_sent_at: string | null
  last_delivery_failed_at: string | null
  delivery_attempts: number
  send_count: number
  created_at: string
  updated_at: string
}

export interface StaffAdministrationClient {
  members(signal?: AbortSignal): Promise<Member[]>
  invitations(signal?: AbortSignal): Promise<StaffInvitation[]>
  issue(email: string): Promise<StaffInvitation>
  resend(invitationId: string): Promise<StaffInvitation>
  revoke(invitationId: string): Promise<StaffInvitation>
}

async function responsePayload<T>(response: Response): Promise<T> {
  try {
    return await response.json() as T
  } catch {
    throw new AuthRequestError('The server returned an unreadable staff-administration response.', response.status)
  }
}

async function requestError(response: Response): Promise<AuthRequestError> {
  const fallback = response.status === 400
    ? 'Enter a valid email address.'
    : response.status === 403
      ? 'Only the installation owner can manage MSP staff invitations.'
      : response.status === 409
        ? 'An active invitation or account already exists for this email address.'
        : response.status === 429
          ? 'Too many invitation changes were attempted. Wait before trying again.'
          : response.status === 503
            ? 'The invitation was retained, but email delivery failed. Review it below and resend it after SMTP is available.'
            : 'Staff administration is unavailable.'
  return privilegedActionError(response, fallback)
}

async function load<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })
  if (!response.ok) throw await requestError(response)
  return responsePayload<T>(response)
}

async function mutate<T>(path: string, body?: object): Promise<T> {
  let csrfToken = browserCsrfToken()
  if (!csrfToken) {
    await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    csrfToken = browserCsrfToken()
  }
  if (!csrfToken) throw new AuthRequestError('The browser security token is unavailable. Refresh and try again.')
  const response = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) throw await requestError(response)
  return responsePayload<T>(response)
}

export const browserStaffAdministrationClient: StaffAdministrationClient = {
  members: (signal) => load<Member[]>('/api/v1/access-control/members', signal),
  invitations: (signal) => load<StaffInvitation[]>('/api/v1/invitations', signal),
  issue: (email) => mutate<StaffInvitation>('/api/v1/invitations', { email }),
  resend: (invitationId) => mutate<StaffInvitation>(`/api/v1/invitations/${encodeURIComponent(invitationId)}/resend`),
  revoke: (invitationId) => mutate<StaffInvitation>(`/api/v1/invitations/${encodeURIComponent(invitationId)}/revoke`),
}
