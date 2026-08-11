import { LogOut } from 'lucide-react'
import type { AuthenticatedContext } from '../auth/api'

export function ClientPortal({ context, onSignOut, signingOut, signOutError }: {
  context: AuthenticatedContext
  onSignOut: () => Promise<void>
  signingOut: boolean
  signOutError: string | null
}) {
  const organization = context.organization
  return (
    <div className="client-portal-shell">
      <header className="client-portal-header">
        <div className="client-portal-brand"><span className="brand-mark" aria-hidden="true">T</span><span>TekDocs</span></div>
        <div className="client-portal-account">
          <span>{context.user.display_name}</span>
          <button className="secondary-button" type="button" disabled={signingOut} onClick={() => { void onSignOut() }}>
            <LogOut size={16} aria-hidden="true" />{signingOut ? 'Signing out…' : 'Sign out'}
          </button>
        </div>
      </header>
      <main className="client-portal-main">
        {signOutError && <div className="form-error" role="alert">{signOutError}</div>}
        <header className="page-header"><div><h1>{organization?.name ?? 'Client portal'}</h1><p>Information explicitly published to your organization.</p></div></header>
        <section className="content-section" aria-labelledby="portal-access-heading">
          <div className="section-heading"><div><h2 id="portal-access-heading">Portal access established</h2><p>Your account is bound to this organization and cannot enter the MSP workspace.</p></div></div>
          <p>Published documentation becomes available in the next portal slice.</p>
        </section>
      </main>
    </div>
  )
}
