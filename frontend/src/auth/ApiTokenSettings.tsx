import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Copy, KeyRound, Plus, RefreshCw, Search, X } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { ApiToken, ApiTokenCatalog, AuthClient, AuthenticatedContext, IssuedApiToken, TokenOrganization } from './api'

function readable(value: string): string {
  return value.replaceAll('_', ' ').replaceAll('.', ' · ')
}

function date(value: string | null): string {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value)) : translate('common.never')
}

function tokenStatus(status: ApiToken['status']): string {
  if (status === 'active') return translate('settings.tokenActive')
  if (status === 'expired') return translate('settings.tokenExpired')
  return translate('settings.tokenRevoked')
}

function tokenKind(kind: ApiToken['kind']): string {
  return kind === 'personal' ? translate('settings.personalToken') : translate('settings.serviceToken')
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
    } catch (reason) { setError(reason instanceof Error ? reason.message : translate('settings.tokensLoadFailed')) }
  }, [client])

  useEffect(() => {
    let active = true
    client.listApiTokens()
      .then((result) => { if (active) { setError(null); setCatalog(result) } })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : translate('settings.tokensLoadFailed')) })
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
    } catch (reason) { setError(reason instanceof Error ? reason.message : translate('settings.tokenCreateFailed')) } finally { setWorking(false) }
  }

  const rotate = async (token: ApiToken) => {
    setWorking(true); setError(null)
    try { setIssued(await client.rotateApiToken(token.id, 90)); await load() } catch (reason) { setError(reason instanceof Error ? reason.message : translate('settings.tokenReplaceFailed')) } finally { setWorking(false) }
  }

  const revoke = async (token: ApiToken) => {
    if (!window.confirm(translate('settings.revokeTokenConfirm', { name: token.name }))) return
    setWorking(true); setError(null)
    try { await client.revokeApiToken(token.id); await load() } catch (reason) { setError(reason instanceof Error ? reason.message : translate('settings.tokenRevokeFailed')) } finally { setWorking(false) }
  }

  return <section className="content-section api-token-settings" aria-labelledby="api-token-heading">
    <div className="section-heading settings-heading">
      <div><h2 id="api-token-heading">{translate('settings.apiTokens')}</h2><p>{translate('settings.apiTokensHelp')}</p></div>
      <button className="secondary-button" type="button" onClick={() => setCreating((value) => !value)}><Plus size={15} aria-hidden="true" />{translate('auth.newToken')}</button>
    </div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {issued && <div className="token-secret" role="alert"><KeyRound size={20} aria-hidden="true" /><div><strong>{translate('settings.copyTokenNow')}</strong><p>{translate('settings.copyTokenHelp')}</p><code>{issued.token}</code></div><button className="secondary-button" type="button" onClick={() => void navigator.clipboard.writeText(issued.token)}><Copy size={14} />{translate('common.copy')}</button><button className="icon-button" type="button" aria-label={translate('settings.dismissToken')} onClick={() => setIssued(null)}><X size={16} /></button></div>}
    {creating && <form className="token-create-form" onSubmit={(event) => void submit(event)}>
      <label>{translate('settings.tokenName')}<input value={name} onChange={(event) => setName(event.target.value)} maxLength={100} required autoFocus /></label>
      <label>{translate('settings.tokenType')}<select value={kind} onChange={(event) => { const next = event.target.value as ApiToken['kind']; setKind(next); if (next === 'service') setPermissions((current) => current.filter((key) => catalog?.permissions.some((permission) => permission.key === key && permission.service_eligible))) }}><option value="personal">{translate('settings.personalToken')}</option>{canManageServices && <option value="service">{translate('settings.serviceToken')}</option>}</select></label>
      <label>{translate('settings.workspace')}<select value={scope} onChange={(event) => { const next = event.target.value as ApiToken['workspace_scope']; setScope(next); setPermissions((current) => next === 'organization' && !current.includes('workspaces.view') ? [...current, 'workspaces.view'] : current); setOrganization(null); setOrganizations([]); setQuery('') }}><option value="msp">{context.tenant.name} · MSP</option><option value="organization">{translate('settings.oneOrganization')}</option></select></label>
      {scope === 'organization' && <div className="token-organization-picker"><label><span>{translate('settings.organization')}</span><span className="search-input"><Search size={15} /><input type="search" value={organization?.name ?? query} onChange={(event) => { setOrganization(null); setOrganizations([]); setQuery(event.target.value) }} placeholder={translate('settings.searchByName')} required={!organization} /></span></label>{query.trim().length >= 2 && organizations.length > 0 && <ul>{organizations.map((item) => <li key={item.id}><button type="button" onClick={() => { setOrganization(item); setQuery(item.name); setOrganizations([]) }}>{item.name}<small>{item.classifications.join(', ')}</small></button></li>)}</ul>}</div>}
      <label>{translate('settings.expiresAfter')}<select value={expires} onChange={(event) => setExpires(Number(event.target.value))}><option value={30}>{translate('settings.days30')}</option><option value={90}>{translate('settings.days90')}</option><option value={180}>{translate('settings.days180')}</option><option value={365}>{translate('settings.days365')}</option></select></label>
      <fieldset><legend>{translate('settings.permissions')}</legend><div className="token-permissions">{catalog?.permissions.filter((permission) => kind === 'personal' || permission.service_eligible).map((permission) => { const required = scope === 'organization' && permission.key === 'workspaces.view'; return <label key={permission.key}><input type="checkbox" checked={permissions.includes(permission.key)} disabled={required} onChange={(event) => setPermissions((current) => event.target.checked ? [...current, permission.key] : current.filter((item) => item !== permission.key))} /><span><strong>{permission.label}</strong><small>{required ? translate('settings.organizationPermissionRequired') : permission.category}</small></span></label> })}</div></fieldset>
      <div className="settings-actions"><button className="primary-button" disabled={working || permissions.length === 0 || (scope === 'organization' && !organization)}>{working ? translate('settings.issuingToken') : translate('settings.issueToken')}</button><button className="secondary-button" type="button" onClick={() => setCreating(false)}>{translate('common.cancel')}</button></div>
    </form>}
    {catalog === null && !error ? <p className="settings-state" role="status">{translate('settings.loadingTokens')}</p> : catalog?.tokens.length === 0 ? <p className="settings-state">{translate('settings.noTokens')}</p> : <ul className="token-list">{catalog?.tokens.map((token) => <li key={token.id}><div><strong>{token.name}</strong><span className={`token-status ${token.status}`}>{tokenStatus(token.status)}</span><p><code>{token.display_prefix}</code> · {tokenKind(token.kind)} · {token.organization?.name ?? `${context.tenant.name} MSP`}</p><p>{token.permissions.map(readable).join(', ')} · {translate('settings.tokenDates', { expires: date(token.expires_at), lastUsed: date(token.last_used_at) })}</p></div>{token.status === 'active' && <div className="settings-actions"><button className="secondary-button" type="button" disabled={working} onClick={() => void rotate(token)}><RefreshCw size={14} />{translate('auth.rotate')}</button><button className="danger-button" type="button" disabled={working} onClick={() => void revoke(token)}>{translate('auth.revoke')}</button></div>}</li>)}</ul>}
  </section>
}
