import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { LoaderCircle } from 'lucide-react'
import { translate } from '../i18n/localization'
import { QRCodeSVG } from 'qrcode.react'
import { AuthRequestError, browserCsrfToken, takeInvitationFromLocation, takePasswordResetFromLocation } from './api'
import type { AuthClient, AuthenticatedContext, BootstrapDetails, InvitationAcceptance, OidcProvider } from './api'

type AuthState =
  | { phase: 'loading' }
  | { phase: 'bootstrap' }
  | { phase: 'sign-in' }
  | { phase: 'mfa-challenge' }
  | { phase: 'invitation'; token: string }
  | { phase: 'invitation-unavailable' }
  | { phase: 'password-reset-request' }
  | { phase: 'password-reset-sent' }
  | { phase: 'password-reset-validating'; key: string }
  | { phase: 'password-reset'; key: string }
  | { phase: 'password-reset-unavailable' }
  | { phase: 'password-reset-complete' }
  | { phase: 'authenticated'; context: AuthenticatedContext }
  | { phase: 'error'; message: string }

type AuthenticatedRenderProps = {
  context: AuthenticatedContext
  signOut: () => Promise<void>
  signingOut: boolean
  signOutError: string | null
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : translate('auth.serviceUnavailable')
}

function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <main className="auth-page">
      <section className="auth-panel">
        <div className="auth-brand"><span className="brand-mark" aria-hidden="true">T</span><span>TekDocs</span></div>
        {children}
      </section>
    </main>
  )
}

function LoadingState() {
  return <AuthFrame><div className="auth-loading" role="status"><LoaderCircle size={20} className="spin" />{translate('auth.checking')}</div></AuthFrame>
}

function ErrorState({ detail, retry }: { detail: string; retry: () => void }) {
  return (
    <AuthFrame>
      <h1>{translate('auth.unavailableHeading')}</h1>
      <p className="auth-intro">{translate('auth.unavailableHelp')}</p>
      <div className="form-error" role="alert">{detail}</div>
      <button className="primary-button auth-submit" type="button" onClick={retry}>{translate('auth.tryAgain')}</button>
    </AuthFrame>
  )
}

function BootstrapForm({ submit }: { submit: (details: BootstrapDetails) => Promise<void> }) {
  const [deploymentToken, setDeploymentToken] = useState('')
  const [tenantName, setTenantName] = useState('')
  const [ownerDisplayName, setOwnerDisplayName] = useState('')
  const [ownerEmail, setOwnerEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (password !== confirmation) {
      setError(translate('auth.passwordMismatch'))
      return
    }
    const details = { deploymentToken, tenantName, ownerEmail, ownerDisplayName, password }
    setDeploymentToken('')
    setPassword('')
    setConfirmation('')
    setSubmitting(true)
    try {
      await submit(details)
    } catch (submitError) {
      setError(message(submitError))
      setSubmitting(false)
    }
  }

  return (
    <AuthFrame>
      <h1>{translate('auth.setupHeading')}</h1>
      <p className="auth-intro">{translate('auth.setupHelp')}</p>
      <form className="auth-form" onSubmit={(event) => { void handleSubmit(event) }}>
        <label>{translate('auth.deploymentToken')}<input value={deploymentToken} onChange={(event) => setDeploymentToken(event.target.value)} autoComplete="off" spellCheck={false} required /></label>
        <div className="bootstrap-token-help" aria-labelledby="bootstrap-token-help-heading">
          <p id="bootstrap-token-help-heading"><strong>{translate('auth.findSetupToken')}</strong></p>
          <p>{translate('auth.runFromEnvDirectory')}</p>
          <pre><code>sed -n 's/^TEKDOCS_BOOTSTRAP_TOKEN=//p' .env</code></pre>
          <p>{translate('auth.productionSecretFile')}</p>
          <pre><code>secret_dir="$(sed -n 's/^TEKDOCS_SECRET_DIRECTORY=//p' .env)" &amp;&amp; cat "$secret_dir/bootstrap_token"</code></pre>
          <p>{translate('auth.setupTokenWarning')}</p>
        </div>
        <label>{translate('auth.mspName')}<input value={tenantName} onChange={(event) => setTenantName(event.target.value)} autoComplete="organization" required /></label>
        <label>{translate('auth.yourName')}<input value={ownerDisplayName} onChange={(event) => setOwnerDisplayName(event.target.value)} autoComplete="name" required /></label>
        <label>{translate('auth.emailAddress')}<input type="email" value={ownerEmail} onChange={(event) => setOwnerEmail(event.target.value)} autoComplete="email" required /></label>
        <label>{translate('auth.password')}<input aria-label={translate('auth.password')} type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" minLength={12} required /><span>{translate('auth.passwordHelp')}</span></label>
        <label>{translate('auth.confirmPassword')}<input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" minLength={12} required /></label>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={submitting}>{submitting ? translate('auth.creatingWorkspace') : translate('auth.createWorkspace')}</button>
      </form>
    </AuthFrame>
  )
}

function RequiredMfaSetup({ client, context, complete }: {
  client: AuthClient
  context: AuthenticatedContext
  complete: (context: AuthenticatedContext) => void
}) {
  const [setup, setSetup] = useState<Awaited<ReturnType<AuthClient['beginTotp']>> | null>(null)
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null)
  const [acknowledged, setAcknowledged] = useState(false)
  const [ready, setReady] = useState(false)
  const [reauthenticationRequired, setReauthenticationRequired] = useState(false)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const accountKind = context.role === 'owner' ? 'owner' : 'administrator'

  useEffect(() => {
    let active = true
    client.loadMfa()
      .then((status) => {
        if (active && status.totpEnabled) complete({ ...context, mfa_enrollment_required: false })
      })
      .catch((loadError: unknown) => active && setError(message(loadError)))
    return () => { active = false }
  }, [client, complete, context])

  const begin = async () => {
    setError(null)
    setWorking(true)
    try {
      setSetup(await client.beginTotp())
    } catch (setupError) {
      if (setupError instanceof AuthRequestError && setupError.status === 401) setReauthenticationRequired(true)
      else setError(message(setupError))
    } finally {
      setWorking(false)
    }
  }

  const confirmPassword = async (event: FormEvent) => {
    event.preventDefault()
    const submittedPassword = password
    setPassword('')
    setError(null)
    setWorking(true)
    try {
      await client.reauthenticate(submittedPassword)
      setReauthenticationRequired(false)
      if (!setup) setSetup(await client.beginTotp())
    } catch (confirmationError) {
      setError(message(confirmationError))
    } finally {
      setWorking(false)
    }
  }

  const activate = async (event: FormEvent) => {
    event.preventDefault()
    const submittedCode = code
    setCode('')
    setError(null)
    setWorking(true)
    try {
      setRecoveryCodes(await client.activateTotp(submittedCode))
      setSetup(null)
    } catch (activationError) {
      if (activationError instanceof AuthRequestError && activationError.status === 401) setReauthenticationRequired(true)
      else setError(message(activationError))
    } finally {
      setWorking(false)
    }
  }

  const recoveryText = recoveryCodes?.join('\n') ?? ''
  const copyRecoveryCodes = async () => {
    try {
      await navigator.clipboard.writeText(recoveryText)
    } catch {
      setError(translate('auth.recoveryCopyFailed'))
    }
  }
  const downloadRecoveryCodes = () => {
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([`${recoveryText}\n`], { type: 'text/plain' }))
    link.download = 'tekdocs-recovery-codes.txt'
    link.click()
    URL.revokeObjectURL(link.href)
  }

  if (ready) {
    return (
      <AuthFrame>
        <h1>{translate('auth.setupComplete')}</h1>
        <p className="auth-intro">{translate('auth.setupCompleteHelp')}</p>
        <button className="primary-button auth-submit" type="button" onClick={() => complete({ ...context, mfa_enrollment_required: false })}>{translate('auth.enterMspWorkspace')}</button>
      </AuthFrame>
    )
  }

  return (
    <AuthFrame>
      <h1>{translate('auth.secureAccount', { accountKind })}</h1>
      <p className="auth-intro">{translate('auth.secureAccountHelp')}</p>
      {error && <div className="form-error" role="alert">{error}</div>}
      {!setup && !recoveryCodes && !reauthenticationRequired && (
        <button className="primary-button auth-submit" type="button" disabled={working} onClick={() => { void begin() }}>{working ? translate('auth.starting') : translate('auth.setupAuthenticator')}</button>
      )}
      {reauthenticationRequired && (
        <form className="auth-form" onSubmit={(event) => { void confirmPassword(event) }}>
          <label>{translate('auth.currentPassword')}<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required autoFocus /></label>
          <button className="primary-button auth-submit" type="submit" disabled={working}>{working ? translate('auth.confirming') : translate('auth.confirmPasswordAction')}</button>
        </form>
      )}
      {setup && !reauthenticationRequired && (
        <form className="auth-form" onSubmit={(event) => { void activate(event) }}>
          <figure className="mfa-qr-code">
            <QRCodeSVG value={setup.totpUrl} size={192} level="M" marginSize={4} aria-hidden="true" />
            <figcaption>{translate('auth.scanAuthenticator')}</figcaption>
          </figure>
          <details className="mfa-manual-setup"><summary>{translate('auth.enterSetupKey')}</summary><code>{setup.secret}</code></details>
          <label>{translate('auth.authenticationCode')}<input value={code} onChange={(event) => setCode(event.target.value)} autoComplete="one-time-code" inputMode="numeric" required autoFocus /></label>
          <button className="primary-button auth-submit" type="submit" disabled={working}>{working ? translate('auth.verifying') : translate('auth.enableTwoFactor')}</button>
        </form>
      )}
      {recoveryCodes && (
        <div className="recovery-codes" role="region" aria-labelledby="required-recovery-heading">
          <div><strong id="required-recovery-heading">{translate('auth.saveRecoveryCodes')}</strong><p>{translate('auth.saveRecoveryCodesHelp')}</p></div>
          <ul>{recoveryCodes.map((recoveryCode) => <li key={recoveryCode}><code>{recoveryCode}</code></li>)}</ul>
          <div className="settings-actions">
            <button className="secondary-button" type="button" onClick={() => { void copyRecoveryCodes() }}>{translate('auth.copyCodes')}</button>
            <button className="secondary-button" type="button" onClick={downloadRecoveryCodes}>{translate('auth.downloadTextFile')}</button>
          </div>
          <label className="recovery-acknowledgement"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />{translate('auth.recoveryCodesSaved')}</label>
          <button className="primary-button" type="button" disabled={!acknowledged} onClick={() => { setRecoveryCodes(null); setReady(true) }}>{translate('auth.continue')}</button>
        </div>
      )}
    </AuthFrame>
  )
}

function SignInForm({ client, submit, forgotPassword }: {
  client: AuthClient
  submit: (email: string, password: string) => Promise<void>
  forgotPassword: () => void
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [providers, setProviders] = useState<OidcProvider[]>([])

  useEffect(() => {
    let active = true
    client.listOidcProviders().then((configured) => {
      if (active) setProviders(configured)
    }).catch(() => undefined)
    return () => { active = false }
  }, [client])

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    const submittedPassword = password
    setPassword('')
    setSubmitting(true)
    try {
      await submit(email, submittedPassword)
    } catch (submitError) {
      setError(message(submitError))
      setSubmitting(false)
    }
  }

  return (
    <AuthFrame>
      <h1>{translate('auth.signInHeading')}</h1>
      <p className="auth-intro">{translate('auth.signInHelp')}</p>
      <form className="auth-form" onSubmit={(event) => { void handleSubmit(event) }}>
        <label>{translate('auth.emailAddress')}<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required autoFocus /></label>
        <label>{translate('auth.password')}<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></label>
        <button className="auth-text-button" type="button" onClick={forgotPassword}>{translate('auth.forgotPassword')}</button>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={submitting}>{submitting ? translate('auth.signingIn') : translate('auth.signIn')}</button>
      </form>
      {providers.length > 0 && (
        <div className="sso-options">
          <span>{translate('auth.or')}</span>
          {providers.map((provider) => (
            <form key={provider.id} method="post" action="/_allauth/browser/v1/auth/provider/redirect">
              <input type="hidden" name="csrfmiddlewaretoken" value={browserCsrfToken() ?? ''} />
              <input type="hidden" name="provider" value={provider.id} />
              <input type="hidden" name="process" value="login" />
              <input type="hidden" name="callback_url" value={`${window.location.origin}/`} />
              <button className="secondary-button auth-submit" type="submit">{translate('auth.continueWith', { provider: provider.name })}</button>
            </form>
          ))}
        </div>
      )}
    </AuthFrame>
  )
}

function MfaChallengeForm({ submit, cancel }: {
  submit: (code: string) => Promise<void>
  cancel: () => void
}) {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    const submittedCode = code
    setCode('')
    setSubmitting(true)
    try {
      await submit(submittedCode)
    } catch (submitError) {
      setError(message(submitError))
      setSubmitting(false)
    }
  }

  return (
    <AuthFrame>
      <h1>{translate('auth.twoFactorHeading')}</h1>
      <p className="auth-intro">{translate('auth.twoFactorChallengeHelp')}</p>
      <form className="auth-form" onSubmit={(event) => { void handleSubmit(event) }}>
        <label>{translate('auth.authenticationCode')}<input value={code} onChange={(event) => setCode(event.target.value)} autoComplete="one-time-code" inputMode="text" spellCheck={false} required autoFocus /></label>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={submitting}>{submitting ? translate('auth.verifying') : translate('auth.verifyCode')}</button>
        <button className="auth-text-button auth-cancel-button" type="button" onClick={cancel}>{translate('auth.returnToSignIn')}</button>
      </form>
    </AuthFrame>
  )
}

function PasswordResetRequestForm({ submit }: { submit: (email: string) => Promise<void> }) {
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await submit(email)
    } catch (submitError) {
      setError(message(submitError))
      setSubmitting(false)
    }
  }

  return (
    <AuthFrame>
      <h1>{translate('auth.resetPasswordHeading')}</h1>
      <p className="auth-intro">{translate('auth.resetPasswordHelp')}</p>
      <form className="auth-form" onSubmit={(event) => { void handleSubmit(event) }}>
        <label>{translate('auth.emailAddress')}<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required autoFocus /></label>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={submitting}>{submitting ? translate('auth.sendingResetLink') : translate('auth.sendResetLink')}</button>
      </form>
      <a className="auth-return-link" href="/">{translate('auth.returnToSignIn')}</a>
    </AuthFrame>
  )
}

function PasswordResetSentState() {
  return (
    <AuthFrame>
      <h1>{translate('auth.checkEmailHeading')}</h1>
      <p className="auth-intro">{translate('auth.checkEmailHelp')}</p>
      <a className="secondary-button auth-submit auth-link" href="/">{translate('auth.returnToSignIn')}</a>
    </AuthFrame>
  )
}

function PasswordResetUnavailableState() {
  return (
    <AuthFrame>
      <h1>{translate('auth.resetLinkUnavailable')}</h1>
      <p className="auth-intro">{translate('auth.resetLinkUnavailableHelp')}</p>
      <a className="primary-button auth-submit auth-link" href="/auth/reset-password">{translate('auth.requestNewResetLink')}</a>
    </AuthFrame>
  )
}

function PasswordResetForm({ submit, unavailable }: {
  submit: (password: string) => Promise<void>
  unavailable: () => void
}) {
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (password !== confirmation) {
      setError(translate('auth.passwordMismatch'))
      return
    }
    const submittedPassword = password
    setPassword('')
    setConfirmation('')
    setSubmitting(true)
    try {
      await submit(submittedPassword)
    } catch (submitError) {
      if (submitError instanceof AuthRequestError && submitError.status === 400) {
        setError(message(submitError))
        setSubmitting(false)
        return
      }
      if (submitError instanceof AuthRequestError && [401, 409].includes(submitError.status ?? 0)) {
        unavailable()
        return
      }
      setError(message(submitError))
      setSubmitting(false)
    }
  }

  return (
    <AuthFrame>
      <h1>{translate('auth.chooseNewPassword')}</h1>
      <p className="auth-intro">{translate('auth.chooseNewPasswordHelp')}</p>
      <form className="auth-form" onSubmit={(event) => { void handleSubmit(event) }}>
        <label>{translate('auth.newPassword')}<input aria-label={translate('auth.newPassword')} type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" minLength={12} required autoFocus /><span>{translate('auth.passwordHelp')}</span></label>
        <label>{translate('auth.confirmNewPassword')}<input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" minLength={12} required /></label>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={submitting}>{submitting ? translate('auth.changingPassword') : translate('auth.changePassword')}</button>
      </form>
    </AuthFrame>
  )
}

function PasswordResetCompleteState() {
  return (
    <AuthFrame>
      <h1>{translate('auth.passwordChanged')}</h1>
      <p className="auth-intro">{translate('auth.passwordChangedHelp')}</p>
      <a className="primary-button auth-submit auth-link" href="/">{translate('auth.continueToSignIn')}</a>
    </AuthFrame>
  )
}

function InvitationUnavailableState() {
  return (
    <AuthFrame>
      <h1>{translate('auth.invitationUnavailable')}</h1>
      <p className="auth-intro">{translate('auth.invitationUnavailableHelp')}</p>
      <a className="secondary-button auth-submit auth-link" href="/">{translate('auth.returnToSignIn')}</a>
    </AuthFrame>
  )
}

function InvitationForm({ token, submit, unavailable }: {
  token: string
  submit: (details: InvitationAcceptance) => Promise<void>
  unavailable: () => void
}) {
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (password !== confirmation) {
      setError(translate('auth.passwordMismatch'))
      return
    }
    const submittedPassword = password
    setPassword('')
    setConfirmation('')
    setSubmitting(true)
    try {
      await submit({ token, displayName, password: submittedPassword })
    } catch (submitError) {
      if (submitError instanceof AuthRequestError && submitError.status === 410) {
        unavailable()
        return
      }
      setError(message(submitError))
      setSubmitting(false)
    }
  }

  return (
    <AuthFrame>
      <h1>{translate('auth.acceptInvitation')}</h1>
      <p className="auth-intro">{translate('auth.acceptInvitationHelp')}</p>
      <form className="auth-form" onSubmit={(event) => { void handleSubmit(event) }}>
        <label>{translate('auth.yourName')}<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} autoComplete="name" required autoFocus /></label>
        <label>{translate('auth.password')}<input aria-label={translate('auth.password')} type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" minLength={12} required /><span>{translate('auth.passwordHelp')}</span></label>
        <label>{translate('auth.confirmPassword')}<input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" minLength={12} required /></label>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={submitting}>{submitting ? translate('auth.activatingAccount') : translate('auth.activateAccount')}</button>
      </form>
    </AuthFrame>
  )
}

export function AuthGate({ client, initialContext, children }: {
  client: AuthClient
  initialContext?: AuthenticatedContext
  children: (props: AuthenticatedRenderProps) => ReactNode
}) {
  const [invitation] = useState(() => takeInvitationFromLocation())
  const [passwordReset] = useState(() => takePasswordResetFromLocation())
  const [state, setState] = useState<AuthState>(() => {
    if (invitation.isInvitationPath) {
      return invitation.token ? { phase: 'invitation', token: invitation.token } : { phase: 'invitation-unavailable' }
    }
    if (passwordReset.isPasswordResetPath) {
      return passwordReset.key
        ? { phase: 'password-reset-validating', key: passwordReset.key }
        : { phase: 'password-reset-request' }
    }
    return initialContext ? { phase: 'authenticated', context: initialContext } : { phase: 'loading' }
  })
  const [signingOut, setSigningOut] = useState(false)
  const [signOutError, setSignOutError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (initialContext || invitation.isInvitationPath || passwordReset.isPasswordResetPath) return
    let current = true
    client.load()
      .then((result) => {
        if (!current) return
        setState(result.bootstrapRequired
          ? { phase: 'bootstrap' }
          : result.context
            ? { phase: 'authenticated', context: result.context }
            : { phase: 'sign-in' })
      })
      .catch((error: unknown) => current && setState({ phase: 'error', message: message(error) }))
    return () => { current = false }
  }, [attempt, client, initialContext, invitation.isInvitationPath, passwordReset.isPasswordResetPath])

  useEffect(() => {
    if (state.phase !== 'password-reset-validating') return
    let current = true
    const key = state.key
    client.validatePasswordReset(key)
      .then(() => current && setState({ phase: 'password-reset', key }))
      .catch(() => current && setState({ phase: 'password-reset-unavailable' }))
    return () => { current = false }
  }, [client, state])

  const bootstrap = async (details: BootstrapDetails) => {
    const authenticated = await client.bootstrapAndLogin(details)
    setState({ phase: 'authenticated', context: authenticated })
  }

  const login = async (email: string, password: string) => {
    const result = await client.login(email, password)
    setState('mfaRequired' in result
      ? { phase: 'mfa-challenge' }
      : { phase: 'authenticated', context: result })
  }

  const acceptInvitation = async (details: InvitationAcceptance) => {
    const authenticated = await client.acceptInvitation(details)
    window.history.replaceState({}, '', '/')
    setState({ phase: 'authenticated', context: authenticated })
  }

  const signOut = async () => {
    setSigningOut(true)
    setSignOutError(null)
    try {
      await client.logout()
      setState({ phase: 'sign-in' })
    } catch (error) {
      setSignOutError(message(error))
    } finally {
      setSigningOut(false)
    }
  }

  if (state.phase === 'loading') return <LoadingState />
  if (state.phase === 'bootstrap') return <BootstrapForm submit={bootstrap} />
  if (state.phase === 'sign-in') return <SignInForm client={client} submit={login} forgotPassword={() => setState({ phase: 'password-reset-request' })} />
  if (state.phase === 'mfa-challenge') return <MfaChallengeForm submit={async (code) => { setState({ phase: 'authenticated', context: await client.completeMfaLogin(code) }) }} cancel={() => setState({ phase: 'sign-in' })} />
  if (state.phase === 'password-reset-request') return <PasswordResetRequestForm submit={async (email) => { await client.requestPasswordReset(email); setState({ phase: 'password-reset-sent' }) }} />
  if (state.phase === 'password-reset-sent') return <PasswordResetSentState />
  if (state.phase === 'password-reset-validating') return <AuthFrame><div className="auth-loading" role="status"><LoaderCircle size={20} className="spin" />{translate('auth.checkingResetLink')}</div></AuthFrame>
  if (state.phase === 'password-reset-unavailable') return <PasswordResetUnavailableState />
  if (state.phase === 'password-reset') return <PasswordResetForm submit={async (password) => { await client.completePasswordReset(state.key, password); setState({ phase: 'password-reset-complete' }) }} unavailable={() => setState({ phase: 'password-reset-unavailable' })} />
  if (state.phase === 'password-reset-complete') return <PasswordResetCompleteState />
  if (state.phase === 'invitation-unavailable') return <InvitationUnavailableState />
  if (state.phase === 'invitation') return <InvitationForm token={state.token} submit={acceptInvitation} unavailable={() => setState({ phase: 'invitation-unavailable' })} />
  if (state.phase === 'error') return <ErrorState detail={state.message} retry={() => { setState({ phase: 'loading' }); setAttempt((value) => value + 1) }} />
  if (state.context.mfa_enrollment_required) {
    return <RequiredMfaSetup client={client} context={state.context} complete={(updated) => setState({ phase: 'authenticated', context: updated })} />
  }
  return children({ context: state.context, signOut, signingOut, signOutError })
}
