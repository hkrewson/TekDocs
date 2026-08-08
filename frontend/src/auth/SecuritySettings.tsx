import { useCallback, useEffect, useState } from 'react'
import { Laptop, RefreshCw } from 'lucide-react'
import type { AuthClient, AuthSession } from './api'

function sessionName(userAgent: string): string {
  const browser = userAgent.includes('Edg/') ? 'Edge' : userAgent.includes('Chrome/') ? 'Chrome' : userAgent.includes('Firefox/') ? 'Firefox' : userAgent.includes('Safari/') ? 'Safari' : 'Browser'
  const platform = userAgent.includes('Android') ? 'Android' : userAgent.includes('iPhone') || userAgent.includes('iPad') ? 'iOS' : userAgent.includes('Windows') ? 'Windows' : userAgent.includes('Mac') ? 'macOS' : userAgent.includes('Linux') ? 'Linux' : ''
  return platform ? `${browser} on ${platform}` : browser
}

function timestamp(value: number): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value * 1000))
}

export function SecuritySettings({ client }: { client: AuthClient }) {
  const [sessions, setSessions] = useState<AuthSession[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [revoking, setRevoking] = useState<number | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setSessions(await client.listSessions())
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Active sessions could not be loaded.')
    }
  }, [client])

  useEffect(() => {
    let active = true
    client.listSessions()
      .then((loaded) => { if (active) setSessions(loaded) })
      .catch((loadError: unknown) => {
        if (active) setError(loadError instanceof Error ? loadError.message : 'Active sessions could not be loaded.')
      })
    return () => { active = false }
  }, [client])

  const revoke = async (session: AuthSession) => {
    setError(null)
    setRevoking(session.id)
    try {
      setSessions(await client.revokeSession(session.id))
    } catch (revokeError) {
      setError(revokeError instanceof Error ? revokeError.message : 'The session could not be revoked.')
    } finally {
      setRevoking(null)
    }
  }

  return (
    <>
      <header className="page-header">
        <div><h1>Settings</h1><p>Manage account security and browsers signed in to TekDocs.</p></div>
      </header>
      <section className="content-section" aria-labelledby="active-sessions-heading">
        <div className="section-heading settings-heading">
          <div><h2 id="active-sessions-heading">Active sessions</h2><p>Revoke any browser you no longer recognize or use.</p></div>
          <button className="secondary-button refresh-button" type="button" onClick={() => { void load() }}><RefreshCw size={15} aria-hidden="true" />Refresh</button>
        </div>
        {error && <div className="form-error settings-error" role="alert">{error}</div>}
        {sessions === null && !error && <p className="settings-state" role="status">Loading active sessions…</p>}
        {sessions?.length === 0 && <p className="settings-state">No active sessions were found.</p>}
        {sessions && sessions.length > 0 && (
          <ul className="session-list">
            {sessions.map((session) => (
              <li key={session.id}>
                <Laptop size={19} aria-hidden="true" />
                <div className="session-details">
                  <div className="session-title"><strong>{sessionName(session.userAgent)}</strong>{session.isCurrent && <span>Current session</span>}</div>
                  <p>{session.ip} · Last active <time dateTime={new Date(session.lastSeenAt * 1000).toISOString()}>{timestamp(session.lastSeenAt)}</time></p>
                  <p>Signed in <time dateTime={new Date(session.createdAt * 1000).toISOString()}>{timestamp(session.createdAt)}</time></p>
                </div>
                {session.isCurrent
                  ? <span className="current-session-note">Sign out from the profile menu</span>
                  : <button className="secondary-button revoke-button" type="button" disabled={revoking === session.id} onClick={() => { void revoke(session) }}>{revoking === session.id ? 'Revoking…' : 'Revoke'}</button>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
