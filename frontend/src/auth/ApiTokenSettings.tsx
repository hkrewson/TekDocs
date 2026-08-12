import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Copy, KeyRound, Plus, RefreshCw, Search, X } from 'lucide-react'
import type { ApiToken, ApiTokenCatalog, AuthClient, AuthenticatedContext, IssuedApiToken, TokenOrganization } from './api'

function readable(value: string): string {
  return value.replaceAll('_', ' ').replaceAll('.', ' · ')
}

function date(value: string | null): string {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value)) : 'Never'
}

export function ApiTokenSettings({ client, context }: { client: AuthClient; context: AuthenticatedContext }) {
  const [catalog, setCatalog] = useState<ApiTokenCatalog | null>(null)
  const [creating, setCreating] = useState(false)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [issued, setIssued] = useState<IssuedApiToken | null>(null)
  const [name, setName] = useState('')
  const [kind, setKind] = useState<ApiToken['kind']>('personal')
  const [scope, setScope] = useState<ApiToken['workspace_scope']>('msp')
  const [permissions, setPermissions] = useState<string[]>([])
  const [expires, setExpires] = useState(90)
  const [query, setQuery] = useState('')
  const [organizations, setOrganizations] = useState<TokenOrganization[]>([])
  const [organization, setOrganization] = useState<TokenOrganization | null>(null)
  const canManageServices = context.permissions.includes('integrations.manage')

  const load = useCallback(async () => {
    try {
      const result = await client.listApiTokens()
      setError(null)
      setCatalog(result)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'API tokens could not be loaded.') }
  }, [client])

  useEffect(() => {
    let active = true
    client.listApiTokens()
      .then((result) => { if (active) { setError(null); setCatalog(result) } })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'API tokens could not be loaded.') })
    return () => { active = false }
  }, [client])

  useEffect(() => {
    if (scope !== 'organization' || query.trim().length < 2 || organization) return
    const timer = window.setTimeout(() => {
      void client.searchTokenOrganizations(query.trim()).then(setOrganizations).catch(() => setOrganizations([]))
    }, 200)
    return () => window.clearTimeout(timer)
  }, [client, organization, query, scope])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setWorking(true)
    try {
      const result = await client.issueApiToken({ name, kind, workspace_scope: scope, organization_id: organization?.id ?? null, permissions, expires_in_days: expires })
      setIssued(result)
      setCreating(false)
      setName('')
      setPermissions([])
      setOrganization(null)
      setQuery('')
      await load()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The API token could not be issued.') } finally { setWorking(false) }
  }

  const rotate = async (token: ApiToken) => {
    setWorking(true); setError(null)
    try { setIssued(await client.rotateApiToken(token.id, 90)); await load() } catch (reason) { setError(reason instanceof Error ? reason.message : 'The API token could not be rotated.') } finally { setWorking(false) }
  }

  const revoke = async (token: ApiToken) => {
    if (!window.confirm(`Revoke “${token.name}”? Existing automation will stop immediately.`)) return
    setWorking(true); setError(null)
    try { await client.revokeApiToken(token.id); await load() } catch (reason) { setError(reason instanceof Error ? reason.message : 'The API token could not be revoked.') } finally { setWorking(false) }
  }

  return <section className="content-section api-token-settings" aria-labelledby="api-token-heading">
    <div className="section-heading settings-heading">
      <div><h2 id="api-token-heading">API tokens</h2><p>Issue expiring credentials for one exact Workspace and an explicit set of permissions. Tokens never expand the account’s access.</p></div>
      <button className="secondary-button" type="button" onClick={() => setCreating((value) => !value)}><Plus size={15} aria-hidden="true" />New token</button>
    </div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {issued && <div className="token-secret" role="alert"><KeyRound size={20} aria-hidden="true" /><div><strong>Copy this token now</strong><p>TekDocs will not display it again.</p><code>{issued.token}</code></div><button className="secondary-button" type="button" onClick={() => void navigator.clipboard.writeText(issued.token)}><Copy size={14} />Copy</button><button className="icon-button" type="button" aria-label="Dismiss token" onClick={() => setIssued(null)}><X size={16} /></button></div>}
    {creating && <form className="token-create-form" onSubmit={(event) => void submit(event)}>
      <label>Name<input value={name} onChange={(event) => setName(event.target.value)} maxLength={100} required autoFocus /></label>
      <label>Token type<select value={kind} onChange={(event) => { const next = event.target.value as ApiToken['kind']; setKind(next); if (next === 'service') setPermissions((current) => current.filter((key) => catalog?.permissions.some((permission) => permission.key === key && permission.service_eligible))) }}><option value="personal">Personal</option>{canManageServices && <option value="service">Service account</option>}</select></label>
      <label>Workspace<select value={scope} onChange={(event) => { const next = event.target.value as ApiToken['workspace_scope']; setScope(next); setPermissions((current) => next === 'organization' && !current.includes('workspaces.view') ? [...current, 'workspaces.view'] : current); setOrganization(null); setOrganizations([]); setQuery('') }}><option value="msp">{context.tenant.name} · MSP</option><option value="organization">One organization</option></select></label>
      {scope === 'organization' && <div className="token-organization-picker"><label><span>Organization</span><span className="search-input"><Search size={15} /><input type="search" value={organization?.name ?? query} onChange={(event) => { setOrganization(null); setOrganizations([]); setQuery(event.target.value) }} placeholder="Search by name" required={!organization} /></span></label>{query.trim().length >= 2 && organizations.length > 0 && <ul>{organizations.map((item) => <li key={item.id}><button type="button" onClick={() => { setOrganization(item); setQuery(item.name); setOrganizations([]) }}>{item.name}<small>{item.classifications.join(', ')}</small></button></li>)}</ul>}</div>}
      <label>Expires after<select value={expires} onChange={(event) => setExpires(Number(event.target.value))}><option value={30}>30 days</option><option value={90}>90 days</option><option value={180}>180 days</option><option value={365}>365 days</option></select></label>
      <fieldset><legend>Permissions</legend><div className="token-permissions">{catalog?.permissions.filter((permission) => kind === 'personal' || permission.service_eligible).map((permission) => { const required = scope === 'organization' && permission.key === 'workspaces.view'; return <label key={permission.key}><input type="checkbox" checked={permissions.includes(permission.key)} disabled={required} onChange={(event) => setPermissions((current) => event.target.checked ? [...current, permission.key] : current.filter((item) => item !== permission.key))} /><span><strong>{permission.label}</strong><small>{required ? 'Required to resolve the selected organization Workspace.' : permission.category}</small></span></label> })}</div></fieldset>
      <div className="settings-actions"><button className="primary-button" disabled={working || permissions.length === 0 || (scope === 'organization' && !organization)}>{working ? 'Issuing…' : 'Issue token'}</button><button className="secondary-button" type="button" onClick={() => setCreating(false)}>Cancel</button></div>
    </form>}
    {catalog === null && !error ? <p className="settings-state" role="status">Loading API tokens…</p> : catalog?.tokens.length === 0 ? <p className="settings-state">No API tokens have been issued.</p> : <ul className="token-list">{catalog?.tokens.map((token) => <li key={token.id}><div><strong>{token.name}</strong><span className={`token-status ${token.status}`}>{token.status}</span><p><code>{token.display_prefix}</code> · {token.kind} · {token.organization?.name ?? `${context.tenant.name} MSP`}</p><p>{token.permissions.map(readable).join(', ')} · expires {date(token.expires_at)} · last used {date(token.last_used_at)}</p></div>{token.status === 'active' && <div className="settings-actions"><button className="secondary-button" type="button" disabled={working} onClick={() => void rotate(token)}><RefreshCw size={14} />Rotate</button><button className="danger-button" type="button" disabled={working} onClick={() => void revoke(token)}>Revoke</button></div>}</li>)}</ul>}
  </section>
}
