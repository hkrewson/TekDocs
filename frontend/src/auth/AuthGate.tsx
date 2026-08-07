import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { LoaderCircle } from 'lucide-react'
import type { AuthClient, AuthenticatedContext, BootstrapDetails } from './api'

type AuthState =
  | { phase: 'loading' }
  | { phase: 'bootstrap' }
  | { phase: 'sign-in' }
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

function SignInForm({ submit }: { submit: (email: string, password: string) => Promise<void> }) {
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
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </AuthFrame>
  )
}

export function AuthGate({ client, initialContext, children }: {
  client: AuthClient
  initialContext?: AuthenticatedContext
  children: (props: AuthenticatedRenderProps) => ReactNode
}) {
  const [state, setState] = useState<AuthState>(initialContext ? { phase: 'authenticated', context: initialContext } : { phase: 'loading' })
  const [signingOut, setSigningOut] = useState(false)
  const [signOutError, setSignOutError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (initialContext) return
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
  }, [attempt, client, initialContext])

  const bootstrap = async (details: BootstrapDetails) => {
    const authenticated = await client.bootstrapAndLogin(details)
    setState({ phase: 'authenticated', context: authenticated })
  }

  const login = async (email: string, password: string) => {
    const authenticated = await client.login(email, password)
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
  if (state.phase === 'sign-in') return <SignInForm submit={login} />
  if (state.phase === 'error') return <ErrorState detail={state.message} retry={() => { setState({ phase: 'loading' }); setAttempt((value) => value + 1) }} />
  return children({ context: state.context, signOut, signingOut, signOutError })
}
