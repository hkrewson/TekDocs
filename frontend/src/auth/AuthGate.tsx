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
  return error instanceof Error ? error.message : 'The authentication service is unavailable.'
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
  return <AuthFrame><div className="auth-loading" role="status"><LoaderCircle size={20} className="spin" />Checking installation…</div></AuthFrame>
}

function ErrorState({ detail, retry }: { detail: string; retry: () => void }) {
  return (
    <AuthFrame>
      <h1>TekDocs is unavailable</h1>
      <p className="auth-intro">The browser could not confirm the installation or session state.</p>
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
      setError('The password confirmation does not match.')
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
      <h1>Set up TekDocs</h1>
      <p className="auth-intro">Create the MSP workspace and its first owner. The deployment token is read from your server’s secret configuration.</p>
      <form className="auth-form" onSubmit={(event) => { void handleSubmit(event) }}>
        <label>Deployment token<input value={deploymentToken} onChange={(event) => setDeploymentToken(event.target.value)} autoComplete="off" spellCheck={false} required /></label>
        <div className="bootstrap-token-help" aria-labelledby="bootstrap-token-help-heading">
          <p id="bootstrap-token-help-heading"><strong>Retrieve the token from the deployment shell</strong></p>
          <p>Run this from the directory containing <code>.env</code>:</p>
          <pre><code>sed -n 's/^TEKDOCS_BOOTSTRAP_TOKEN=//p' .env</code></pre>
          <p>For a production secret-file deployment:</p>
          <pre><code>secret_dir="$(sed -n 's/^TEKDOCS_SECRET_DIRECTORY=//p' .env)" &amp;&amp; cat "$secret_dir/bootstrap_token"</code></pre>
          <p>Paste the output above. Do not share or save it in documentation.</p>
        </div>
        <label>MSP name<input value={tenantName} onChange={(event) => setTenantName(event.target.value)} autoComplete="organization" required /></label>
        <label>Your name<input value={ownerDisplayName} onChange={(event) => setOwnerDisplayName(event.target.value)} autoComplete="name" required /></label>
        <label>Email address<input type="email" value={ownerEmail} onChange={(event) => setOwnerEmail(event.target.value)} autoComplete="email" required /></label>
        <label>Password<input aria-label="Password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" minLength={12} required /><span>Use at least 12 characters and a unique password.</span></label>
        <label>Confirm password<input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" minLength={12} required /></label>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={submitting}>{submitting ? 'Creating workspace…' : 'Create workspace'}</button>
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
      setError('Recovery codes could not be copied. Save them manually before continuing.')
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
        <h1>Setup complete</h1>
        <p className="auth-intro">Two-factor authentication is enabled. Remove the bootstrap overlay and bootstrap-token file from the deployment after confirming this account can sign in.</p>
        <button className="primary-button auth-submit" type="button" onClick={() => complete({ ...context, mfa_enrollment_required: false })}>{translate('auth.enterMspWorkspace')}</button>
      </AuthFrame>
    )
  }

  return (
    <AuthFrame>
      <h1>Secure the {accountKind} account</h1>
      <p className="auth-intro">Two-factor authentication is required before privileged TekDocs actions are available.</p>
      {error && <div className="form-error" role="alert">{error}</div>}
      {!setup && !recoveryCodes && !reauthenticationRequired && (
        <button className="primary-button auth-submit" type="button" disabled={working} onClick={() => { void begin() }}>{working ? 'Starting…' : 'Set up authenticator'}</button>
      )}
      {reauthenticationRequired && (
        <form className="auth-form" onSubmit={(event) => { void confirmPassword(event) }}>
          <label>Current password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required autoFocus /></label>
          <button className="primary-button auth-submit" type="submit" disabled={working}>{working ? 'Confirming…' : 'Confirm password'}</button>
        </form>
      )}
      {setup && !reauthenticationRequired && (
        <form className="auth-form" onSubmit={(event) => { void activate(event) }}>
          <figure className="mfa-qr-code">
            <QRCodeSVG value={setup.totpUrl} size={192} level="M" marginSize={4} aria-hidden="true" />
            <figcaption>Scan with your authenticator app</figcaption>
          </figure>
          <details className="mfa-manual-setup"><summary>Enter a setup key manually</summary><code>{setup.secret}</code></details>
          <label>Authentication code<input value={code} onChange={(event) => setCode(event.target.value)} autoComplete="one-time-code" inputMode="numeric" required autoFocus /></label>
          <button className="primary-button auth-submit" type="submit" disabled={working}>{working ? 'Verifying…' : 'Enable two-factor authentication'}</button>
        </form>
      )}
      {recoveryCodes && (
        <div className="recovery-codes" role="region" aria-labelledby="required-recovery-heading">
          <div><strong id="required-recovery-heading">Save these recovery codes now</strong><p>They will not be shown again. Store them separately from your password.</p></div>
          <ul>{recoveryCodes.map((recoveryCode) => <li key={recoveryCode}><code>{recoveryCode}</code></li>)}</ul>
          <div className="settings-actions">
            <button className="secondary-button" type="button" onClick={() => { void copyRecoveryCodes() }}>{translate('auth.copyCodes')}</button>
            <button className="secondary-button" type="button" onClick={downloadRecoveryCodes}>{translate('auth.downloadTextFile')}</button>
          </div>
          <label className="recovery-acknowledgement"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />I saved the recovery codes in a secure location.</label>
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
      <h1>Sign in</h1>
      <p className="auth-intro">Use your TekDocs owner account.</p>
      <form className="auth-form" onSubmit={(event) => { void handleSubmit(event) }}>
        <label>Email address<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required autoFocus /></label>
        <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></label>
        <button className="auth-text-button" type="button" onClick={forgotPassword}>{translate('auth.forgotPassword')}</button>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</button>
      </form>
      {providers.length > 0 && (
        <div className="sso-options">
          <span>or</span>
          {providers.map((provider) => (
            <form key={provider.id} method="post" action="/_allauth/browser/v1/auth/provider/redirect">
              <input type="hidden" name="csrfmiddlewaretoken" value={browserCsrfToken() ?? ''} />
              <input type="hidden" name="provider" value={provider.id} />
              <input type="hidden" name="process" value="login" />
              <input type="hidden" name="callback_url" value={`${window.location.origin}/`} />
              <button className="secondary-button auth-submit" type="submit">Continue with {provider.name}</button>
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
      <h1>Two-factor authentication</h1>
      <p className="auth-intro">Enter the current code from your authenticator app, or use one recovery code.</p>
      <form className="auth-form" onSubmit={(event) => { void handleSubmit(event) }}>
        <label>Authentication code<input value={code} onChange={(event) => setCode(event.target.value)} autoComplete="one-time-code" inputMode="text" spellCheck={false} required autoFocus /></label>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={submitting}>{submitting ? 'Verifying…' : 'Verify code'}</button>
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
      <h1>Reset password</h1>
      <p className="auth-intro">Enter your account email. If it belongs to an active account, TekDocs will send a reset link.</p>
      <form className="auth-form" onSubmit={(event) => { void handleSubmit(event) }}>
        <label>Email address<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required autoFocus /></label>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={submitting}>{submitting ? 'Sending reset link…' : 'Send reset link'}</button>
      </form>
      <a className="auth-return-link" href="/">Return to sign in</a>
    </AuthFrame>
  )
}

function PasswordResetSentState() {
  return (
    <AuthFrame>
      <h1>Check your email</h1>
      <p className="auth-intro">If that address belongs to an active account, a password reset link has been sent. The same message is shown for every address.</p>
      <a className="secondary-button auth-submit auth-link" href="/">Return to sign in</a>
    </AuthFrame>
  )
}

function PasswordResetUnavailableState() {
  return (
    <AuthFrame>
      <h1>Reset link unavailable</h1>
      <p className="auth-intro">This password reset link is invalid, expired, or has already been used.</p>
      <a className="primary-button auth-submit auth-link" href="/auth/reset-password">Request a new reset link</a>
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
      setError('The password confirmation does not match.')
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
      <h1>Choose a new password</h1>
      <p className="auth-intro">Changing your password signs out any existing TekDocs sessions.</p>
      <form className="auth-form" onSubmit={(event) => { void handleSubmit(event) }}>
        <label>New password<input aria-label="New password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" minLength={12} required autoFocus /><span>Use at least 12 characters and a unique password.</span></label>
        <label>Confirm new password<input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" minLength={12} required /></label>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={submitting}>{submitting ? 'Changing password…' : 'Change password'}</button>
      </form>
    </AuthFrame>
  )
}

function PasswordResetCompleteState() {
  return (
    <AuthFrame>
      <h1>Password changed</h1>
      <p className="auth-intro">Your password has been changed and existing sessions are no longer valid. Sign in with the new password.</p>
      <a className="primary-button auth-submit auth-link" href="/">Continue to sign in</a>
    </AuthFrame>
  )
}

function InvitationUnavailableState() {
  return (
    <AuthFrame>
      <h1>Invitation unavailable</h1>
      <p className="auth-intro">This invitation is missing, expired, revoked, or has already been used. Ask the TekDocs owner for a new invitation.</p>
      <a className="secondary-button auth-submit auth-link" href="/">Return to sign in</a>
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
      setError('The password confirmation does not match.')
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
      <h1>Accept invitation</h1>
      <p className="auth-intro">Create your TekDocs account. Your email address is fixed by the invitation.</p>
      <form className="auth-form" onSubmit={(event) => { void handleSubmit(event) }}>
        <label>Your name<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} autoComplete="name" required autoFocus /></label>
        <label>Password<input aria-label="Password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" minLength={12} required /><span>Use at least 12 characters and a unique password.</span></label>
        <label>Confirm password<input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" minLength={12} required /></label>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={submitting}>{submitting ? 'Activating account…' : 'Activate account'}</button>
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
  if (state.phase === 'password-reset-validating') return <AuthFrame><div className="auth-loading" role="status"><LoaderCircle size={20} className="spin" />Checking reset link…</div></AuthFrame>
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
