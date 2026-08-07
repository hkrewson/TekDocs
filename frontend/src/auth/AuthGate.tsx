import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { LoaderCircle } from 'lucide-react'
import { AuthRequestError, takeInvitationFromLocation, takePasswordResetFromLocation } from './api'
import type { AuthClient, AuthenticatedContext, BootstrapDetails, InvitationAcceptance } from './api'

type AuthState =
  | { phase: 'loading' }
  | { phase: 'bootstrap' }
  | { phase: 'sign-in' }
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
      <button className="primary-button auth-submit" type="button" onClick={retry}>Try again</button>
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

function SignInForm({ submit, forgotPassword }: {
  submit: (email: string, password: string) => Promise<void>
  forgotPassword: () => void
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

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
        <button className="auth-text-button" type="button" onClick={forgotPassword}>Forgot password?</button>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</button>
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
    const authenticated = await client.login(email, password)
    setState({ phase: 'authenticated', context: authenticated })
  }

  const acceptInvitation = async (details: InvitationAcceptance) => {
    const authenticated = await client.acceptInvitation(details)
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
  if (state.phase === 'sign-in') return <SignInForm submit={login} forgotPassword={() => setState({ phase: 'password-reset-request' })} />
  if (state.phase === 'password-reset-request') return <PasswordResetRequestForm submit={async (email) => { await client.requestPasswordReset(email); setState({ phase: 'password-reset-sent' }) }} />
  if (state.phase === 'password-reset-sent') return <PasswordResetSentState />
  if (state.phase === 'password-reset-validating') return <AuthFrame><div className="auth-loading" role="status"><LoaderCircle size={20} className="spin" />Checking reset link…</div></AuthFrame>
  if (state.phase === 'password-reset-unavailable') return <PasswordResetUnavailableState />
  if (state.phase === 'password-reset') return <PasswordResetForm submit={async (password) => { await client.completePasswordReset(state.key, password); setState({ phase: 'password-reset-complete' }) }} unavailable={() => setState({ phase: 'password-reset-unavailable' })} />
  if (state.phase === 'password-reset-complete') return <PasswordResetCompleteState />
  if (state.phase === 'invitation-unavailable') return <InvitationUnavailableState />
  if (state.phase === 'invitation') return <InvitationForm token={state.token} submit={acceptInvitation} unavailable={() => setState({ phase: 'invitation-unavailable' })} />
  if (state.phase === 'error') return <ErrorState detail={state.message} retry={() => { setState({ phase: 'loading' }); setAttempt((value) => value + 1) }} />
  return children({ context: state.context, signOut, signingOut, signOutError })
}
