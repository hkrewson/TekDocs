import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { KeyRound, Laptop, RefreshCw, ShieldCheck } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { AuthRequestError } from './api'
import type { AuthClient, AuthenticatedContext, AuthSession, MfaStatus, TotpSetup } from './api'
import { ApiTokenSettings } from './ApiTokenSettings'
import { formatDateTime, translate } from '../i18n/localization'

function sessionName(userAgent: string): string {
  const browser = userAgent.includes('Edg/') ? 'Edge' : userAgent.includes('Chrome/') ? 'Chrome' : userAgent.includes('Firefox/') ? 'Firefox' : userAgent.includes('Safari/') ? 'Safari' : 'Browser'
  const platform = userAgent.includes('Android') ? 'Android' : userAgent.includes('iPhone') || userAgent.includes('iPad') ? 'iOS' : userAgent.includes('Windows') ? 'Windows' : userAgent.includes('Mac') ? 'macOS' : userAgent.includes('Linux') ? 'Linux' : ''
  return platform ? `${browser} on ${platform}` : browser
}

function timestamp(value: number): string {
  return formatDateTime(new Date(value * 1000))
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

type SensitiveAction = 'enroll' | 'activate' | 'replace-codes' | 'disable'

export function SecuritySettings({ client, context, onProfileUpdated }: {
  client: AuthClient
  context: AuthenticatedContext
  onProfileUpdated: (context: AuthenticatedContext) => void
}) {
  const [displayName, setDisplayName] = useState(context.user.display_name)
  const [profileMessage, setProfileMessage] = useState<string | null>(null)
  const [savingProfile, setSavingProfile] = useState(false)
  const [sessions, setSessions] = useState<AuthSession[] | null>(null)
  const [mfa, setMfa] = useState<MfaStatus | null>(null)
  const [setup, setSetup] = useState<TotpSetup | null>(null)
  const [activationCode, setActivationCode] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null)
  const [sensitiveAction, setSensitiveAction] = useState<SensitiveAction | null>(null)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [mfaMessage, setMfaMessage] = useState<string | null>(null)
  const [working, setWorking] = useState(false)
  const [revoking, setRevoking] = useState<number | null>(null)

  const loadSessions = useCallback(async () => {
    setError(null)
    try {
      setSessions(await client.listSessions())
    } catch (loadError) {
      setError(errorMessage(loadError, translate('settings.sessionsLoadFailed')))
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
        if (active) setError(errorMessage(loadError, translate('settings.securityLoadFailed')))
      })
    return () => { active = false }
  }, [client])

  const beginSetup = async () => {
    setError(null)
    setMfaMessage(null)
    setWorking(true)
    try {
      setSetup(await client.beginTotp())
    } catch (setupError) {
      if (setupError instanceof AuthRequestError && setupError.status === 401) {
        setSensitiveAction('enroll')
      } else {
        setError(errorMessage(setupError, translate('settings.authenticatorStartFailed')))
      }
    } finally {
      setWorking(false)
    }
  }

  const activate = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setMfaMessage(null)
    setWorking(true)
    const submittedCode = activationCode
    setActivationCode('')
    try {
      const codes = await client.activateTotp(submittedCode)
      setSetup(null)
      setRecoveryCodes(codes)
      setMfa({ totpEnabled: true, recoveryCodeTotal: codes.length, recoveryCodeUnused: codes.length })
    } catch (activationError) {
      if (activationError instanceof AuthRequestError && activationError.status === 401) {
        setSensitiveAction('activate')
      } else {
        setError(errorMessage(activationError, translate('settings.authenticatorCodeRejected')))
      }
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
      } else if (sensitiveAction === 'activate') {
        setMfaMessage(translate('settings.passwordConfirmed'))
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
      setError(errorMessage(actionError, translate('settings.securityChangeFailed')))
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
      setError(errorMessage(revokeError, translate('settings.sessionSignOutFailed')))
    } finally {
      setRevoking(null)
    }
  }

  const saveProfile = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setProfileMessage(null)
    setSavingProfile(true)
    try {
      const updated = await client.updateProfile(displayName)
      setDisplayName(updated.user.display_name)
      onProfileUpdated(updated)
      setProfileMessage(translate('settings.profileUpdated'))
    } catch (profileError) {
      setError(errorMessage(profileError, translate('settings.profileUpdateFailed')))
    } finally {
      setSavingProfile(false)
    }
  }

  return (
    <>
      <header className="page-header">
        <div><h1>{translate('settings.heading')}</h1></div>
      </header>
      {error && <div className="form-error settings-error" role="alert">{error}</div>}
      <section className="content-section profile-section" aria-labelledby="profile-heading">
        <div className="section-heading settings-heading">
          <div><h2 id="profile-heading">{translate('settings.profile')}</h2><p>{translate('settings.profileHelp')}</p></div>
        </div>
        <form className="profile-settings-form" onSubmit={(event) => { void saveProfile(event) }}>
          <label>{translate('settings.displayName')}<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} autoComplete="name" maxLength={160} required /></label>
          <label>{translate('auth.emailAddress')}<input value={context.user.email} readOnly aria-readonly="true" /></label>
          <div className="settings-actions">
            <button className="primary-button" type="submit" disabled={savingProfile || displayName.trim() === context.user.display_name}>{savingProfile ? translate('common.saving') : translate('settings.saveProfile')}</button>
            {profileMessage && <span className="settings-success" role="status">{profileMessage}</span>}
          </div>
        </form>
      </section>
      <section className="content-section security-section" aria-labelledby="two-factor-heading">
        <div className="section-heading settings-heading">
          <div><h2 id="two-factor-heading">{translate('auth.twoFactorHeading')}</h2><p>{translate('settings.twoFactorHelp')}</p></div>
          {mfa?.totpEnabled && <span className="security-status"><ShieldCheck size={15} aria-hidden="true" />{translate('settings.enabled')}</span>}
        </div>
        {mfa === null && !error && <p className="settings-state" role="status">{translate('settings.loadingTwoFactor')}</p>}
        {mfa && !mfa.totpEnabled && !setup && (
          <div className="security-row">
            <div><strong>{translate('settings.authenticatorApp')}</strong><p>{translate('settings.authenticatorRequired')}</p></div>
            <button className="primary-button" type="button" disabled={working} onClick={() => { void beginSetup() }}>{working ? translate('auth.starting') : translate('auth.setupAuthenticator')}</button>
          </div>
        )}
        {mfaMessage && <p className="settings-success" role="status">{mfaMessage}</p>}
        {setup && sensitiveAction !== 'activate' && (
          <form className="mfa-setup" onSubmit={(event) => { void activate(event) }}>
            <div><strong>{translate('settings.addAuthenticator')}</strong><p>{translate('settings.addAuthenticatorHelp')}</p></div>
            <div className="mfa-enrollment">
              <figure className="mfa-qr-code">
                <QRCodeSVG value={setup.totpUrl} size={192} level="M" marginSize={4} aria-hidden="true" />
                <figcaption>{translate('auth.scanAuthenticator')}</figcaption>
              </figure>
              <div className="mfa-manual-setup">
                <div><strong>{translate('settings.cannotScan')}</strong><p>{translate('settings.manualSetupHelp')}</p></div>
                <div className="mfa-setup-value"><span>{translate('settings.manualKey')}</span><code>{setup.secret}</code></div>
                <details>
                  <summary>{translate('settings.showSetupAddress')}</summary>
                  <code>{setup.totpUrl}</code>
                </details>
              </div>
            </div>
            <label>{translate('auth.authenticationCode')}<input value={activationCode} onChange={(event) => setActivationCode(event.target.value)} autoComplete="one-time-code" inputMode="numeric" required autoFocus /></label>
            <div className="settings-actions">
              <button className="primary-button" type="submit" disabled={working}>{working ? translate('auth.verifying') : translate('auth.enableTwoFactor')}</button>
              <button className="secondary-button" type="button" disabled={working} onClick={() => { setSetup(null); setActivationCode('') }}>{translate('common.cancel')}</button>
            </div>
          </form>
        )}
        {mfa?.totpEnabled && !recoveryCodes && !sensitiveAction && (
          <div className="security-row">
            <div><strong>{translate('settings.recoveryCodes')}</strong><p>{translate('settings.codesRemaining', { unused: mfa.recoveryCodeUnused, total: mfa.recoveryCodeTotal })}</p></div>
            <div className="settings-actions">
              <button className="secondary-button" type="button" onClick={() => setSensitiveAction('replace-codes')}>{translate('auth.replaceCodes')}</button>
              <button className="danger-button" type="button" onClick={() => setSensitiveAction('disable')}>{translate('auth.disable')}</button>
            </div>
          </div>
        )}
        {recoveryCodes && (
          <div className="recovery-codes" role="region" aria-labelledby="recovery-codes-heading">
            <div><strong id="recovery-codes-heading">{translate('auth.saveRecoveryCodes')}</strong><p>{translate('auth.saveRecoveryCodesHelp')}</p></div>
            <ul>{recoveryCodes.map((code) => <li key={code}><code>{code}</code></li>)}</ul>
            <button className="primary-button" type="button" onClick={() => setRecoveryCodes(null)}>{translate('auth.iSavedTheseCodes')}</button>
          </div>
        )}
        {sensitiveAction && (
          <form className="reauth-form" onSubmit={(event) => { void confirmSensitiveAction(event) }}>
            <KeyRound size={19} aria-hidden="true" />
            <div><strong>{translate('settings.confirmYourPassword')}</strong><p>{sensitiveAction === 'disable' ? translate('settings.disableTwoFactorHelp') : sensitiveAction === 'replace-codes' ? translate('settings.replaceCodesHelp') : sensitiveAction === 'activate' ? translate('settings.activationExpiredHelp') : translate('settings.enrollmentPasswordHelp')}</p></div>
            <label>{translate('auth.currentPassword')}<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required autoFocus /></label>
            <div className="settings-actions">
              <button className="primary-button" type="submit" disabled={working}>{working ? translate('auth.confirming') : translate('settings.confirmChange')}</button>
              <button className="secondary-button" type="button" disabled={working} onClick={() => { setSensitiveAction(null); setPassword('') }}>{translate('common.cancel')}</button>
            </div>
          </form>
        )}
      </section>
      <section className="content-section" aria-labelledby="active-sessions-heading">
        <div className="section-heading settings-heading">
          <div><h2 id="active-sessions-heading">{translate('settings.activeSessions')}</h2><p>{translate('settings.activeSessionsHelp')}</p></div>
          <button className="secondary-button refresh-button" type="button" onClick={() => { void loadSessions() }}><RefreshCw size={15} aria-hidden="true" />{translate('common.refresh')}</button>
        </div>
        {sessions === null && !error && <p className="settings-state" role="status">{translate('settings.loadingSessions')}</p>}
        {sessions?.length === 0 && <p className="settings-state">{translate('settings.noSessions')}</p>}
        {sessions && sessions.length > 0 && (
          <ul className="session-list">
            {sessions.map((session) => (
              <li key={session.id}>
                <Laptop size={19} aria-hidden="true" />
                <div className="session-details">
                  <div className="session-title"><strong>{sessionName(session.userAgent)}</strong>{session.isCurrent && <span>{translate('settings.currentSession')}</span>}</div>
                  <p>{session.ip} · {translate('settings.lastActive')} <time dateTime={new Date(session.lastSeenAt * 1000).toISOString()}>{timestamp(session.lastSeenAt)}</time></p>
                  <p>{translate('settings.signedIn')} <time dateTime={new Date(session.createdAt * 1000).toISOString()}>{timestamp(session.createdAt)}</time></p>
                </div>
                {session.isCurrent
                  ? <span className="current-session-note">{translate('settings.signOutCurrent')}</span>
                  : <button className="secondary-button revoke-button" type="button" disabled={revoking === session.id} onClick={() => { void revoke(session) }}>{revoking === session.id ? translate('settings.revoking') : translate('settings.signOutSession')}</button>}
              </li>
            ))}
          </ul>
        )}
      </section>
      {context.surface === 'msp' && <ApiTokenSettings client={client} context={context} />}
    </>
  )
}
