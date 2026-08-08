import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { KeyRound, Laptop, RefreshCw, ShieldCheck } from 'lucide-react'
import { AuthRequestError } from './api'
import type { AuthClient, AuthSession, MfaStatus, TotpSetup } from './api'

function sessionName(userAgent: string): string {
  const browser = userAgent.includes('Edg/') ? 'Edge' : userAgent.includes('Chrome/') ? 'Chrome' : userAgent.includes('Firefox/') ? 'Firefox' : userAgent.includes('Safari/') ? 'Safari' : 'Browser'
  const platform = userAgent.includes('Android') ? 'Android' : userAgent.includes('iPhone') || userAgent.includes('iPad') ? 'iOS' : userAgent.includes('Windows') ? 'Windows' : userAgent.includes('Mac') ? 'macOS' : userAgent.includes('Linux') ? 'Linux' : ''
  return platform ? `${browser} on ${platform}` : browser
}

function timestamp(value: number): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value * 1000))
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

type SensitiveAction = 'enroll' | 'replace-codes' | 'disable'

export function SecuritySettings({ client }: { client: AuthClient }) {
  const [sessions, setSessions] = useState<AuthSession[] | null>(null)
  const [mfa, setMfa] = useState<MfaStatus | null>(null)
  const [setup, setSetup] = useState<TotpSetup | null>(null)
  const [activationCode, setActivationCode] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null)
  const [sensitiveAction, setSensitiveAction] = useState<SensitiveAction | null>(null)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [working, setWorking] = useState(false)
  const [revoking, setRevoking] = useState<number | null>(null)

  const loadSessions = useCallback(async () => {
    setError(null)
    try {
      setSessions(await client.listSessions())
    } catch (loadError) {
      setError(errorMessage(loadError, 'Active sessions could not be loaded.'))
    }
  }, [client])

  useEffect(() => {
    let active = true
    Promise.all([client.listSessions(), client.loadMfa()])
      .then(([loadedSessions, loadedMfa]) => {
        if (active) {
          setSessions(loadedSessions)
          setMfa(loadedMfa)
        }
      })
      .catch((loadError: unknown) => {
        if (active) setError(errorMessage(loadError, 'Security settings could not be loaded.'))
      })
    return () => { active = false }
  }, [client])

  const beginSetup = async () => {
    setError(null)
    setWorking(true)
    try {
      setSetup(await client.beginTotp())
    } catch (setupError) {
      if (setupError instanceof AuthRequestError && setupError.status === 401) {
        setSensitiveAction('enroll')
      } else {
        setError(errorMessage(setupError, 'Authenticator setup could not be started.'))
      }
    } finally {
      setWorking(false)
    }
  }

  const activate = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setWorking(true)
    const submittedCode = activationCode
    setActivationCode('')
    try {
      const codes = await client.activateTotp(submittedCode)
      setSetup(null)
      setRecoveryCodes(codes)
      setMfa({ totpEnabled: true, recoveryCodeTotal: codes.length, recoveryCodeUnused: codes.length })
    } catch (activationError) {
      setError(errorMessage(activationError, 'That authenticator code was not accepted.'))
    } finally {
      setWorking(false)
    }
  }

  const confirmSensitiveAction = async (event: FormEvent) => {
    event.preventDefault()
    if (!sensitiveAction) return
    setError(null)
    setWorking(true)
    const submittedPassword = password
    setPassword('')
    try {
      await client.reauthenticate(submittedPassword)
      if (sensitiveAction === 'enroll') {
        setSetup(await client.beginTotp())
      } else if (sensitiveAction === 'replace-codes') {
        const codes = await client.regenerateRecoveryCodes()
        setRecoveryCodes(codes)
        setMfa((current) => current && { ...current, recoveryCodeTotal: codes.length, recoveryCodeUnused: codes.length })
      } else {
        await client.disableTotp()
        setMfa({ totpEnabled: false, recoveryCodeTotal: 0, recoveryCodeUnused: 0 })
        setRecoveryCodes(null)
      }
      setSensitiveAction(null)
    } catch (actionError) {
      setError(errorMessage(actionError, 'The security change was not completed.'))
    } finally {
      setWorking(false)
    }
  }

  const revoke = async (session: AuthSession) => {
    setError(null)
    setRevoking(session.id)
    try {
      setSessions(await client.revokeSession(session.id))
    } catch (revokeError) {
      setError(errorMessage(revokeError, 'The session could not be revoked.'))
    } finally {
      setRevoking(null)
    }
  }

  return (
    <>
      <header className="page-header">
        <div><h1>Settings</h1><p>Manage account security and browsers signed in to TekDocs.</p></div>
      </header>
      {error && <div className="form-error settings-error" role="alert">{error}</div>}
      <section className="content-section security-section" aria-labelledby="two-factor-heading">
        <div className="section-heading settings-heading">
          <div><h2 id="two-factor-heading">Two-factor authentication</h2><p>Protect your account with a time-based authenticator and single-use recovery codes.</p></div>
          {mfa?.totpEnabled && <span className="security-status"><ShieldCheck size={15} aria-hidden="true" />Enabled</span>}
        </div>
        {mfa === null && !error && <p className="settings-state" role="status">Loading two-factor settings…</p>}
        {mfa && !mfa.totpEnabled && !setup && (
          <div className="security-row">
            <div><strong>Authenticator app</strong><p>Owners must enable this before using privileged administrative actions.</p></div>
            <button className="primary-button" type="button" disabled={working} onClick={() => { void beginSetup() }}>{working ? 'Starting…' : 'Set up authenticator'}</button>
          </div>
        )}
        {setup && (
          <form className="mfa-setup" onSubmit={(event) => { void activate(event) }}>
            <div><strong>Add TekDocs to your authenticator</strong><p>Scan the setup address with your authenticator app, or enter the key manually. Then enter the current code.</p></div>
            <label>Setup address<code>{setup.totpUrl}</code></label>
            <label>Manual key<code>{setup.secret}</code></label>
            <label>Authentication code<input value={activationCode} onChange={(event) => setActivationCode(event.target.value)} autoComplete="one-time-code" inputMode="numeric" required autoFocus /></label>
            <div className="settings-actions">
              <button className="primary-button" type="submit" disabled={working}>{working ? 'Verifying…' : 'Enable two-factor authentication'}</button>
              <button className="secondary-button" type="button" disabled={working} onClick={() => { setSetup(null); setActivationCode('') }}>Cancel</button>
            </div>
          </form>
        )}
        {mfa?.totpEnabled && !recoveryCodes && !sensitiveAction && (
          <div className="security-row">
            <div><strong>Recovery codes</strong><p>{mfa.recoveryCodeUnused} of {mfa.recoveryCodeTotal} codes remain. Each code works once.</p></div>
            <div className="settings-actions">
              <button className="secondary-button" type="button" onClick={() => setSensitiveAction('replace-codes')}>Replace codes</button>
              <button className="danger-button" type="button" onClick={() => setSensitiveAction('disable')}>Disable</button>
            </div>
          </div>
        )}
        {recoveryCodes && (
          <div className="recovery-codes" role="region" aria-labelledby="recovery-codes-heading">
            <div><strong id="recovery-codes-heading">Save these recovery codes now</strong><p>They will not be shown again. Store them somewhere separate from your password.</p></div>
            <ul>{recoveryCodes.map((code) => <li key={code}><code>{code}</code></li>)}</ul>
            <button className="primary-button" type="button" onClick={() => setRecoveryCodes(null)}>I saved these codes</button>
          </div>
        )}
        {sensitiveAction && (
          <form className="reauth-form" onSubmit={(event) => { void confirmSensitiveAction(event) }}>
            <KeyRound size={19} aria-hidden="true" />
            <div><strong>Confirm your password</strong><p>{sensitiveAction === 'disable' ? 'Disabling two-factor authentication also invalidates existing recovery codes.' : sensitiveAction === 'replace-codes' ? 'Replacing recovery codes invalidates every previous code.' : 'Authenticator enrollment requires a recent password check.'}</p></div>
            <label>Current password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required autoFocus /></label>
            <div className="settings-actions">
              <button className="primary-button" type="submit" disabled={working}>{working ? 'Confirming…' : 'Confirm change'}</button>
              <button className="secondary-button" type="button" disabled={working} onClick={() => { setSensitiveAction(null); setPassword('') }}>Cancel</button>
            </div>
          </form>
        )}
      </section>
      <section className="content-section" aria-labelledby="active-sessions-heading">
        <div className="section-heading settings-heading">
          <div><h2 id="active-sessions-heading">Active sessions</h2><p>Revoke any browser you no longer recognize or use.</p></div>
          <button className="secondary-button refresh-button" type="button" onClick={() => { void loadSessions() }}><RefreshCw size={15} aria-hidden="true" />Refresh</button>
        </div>
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
