import type { WorkspaceContext } from '../workspaces/api'

export type RegisteredDomain = {
  id: string
  name: string
  registrar_id: string | null
  registrar: string | null
  registration_date: string | null
  expiration_date: string | null
  renewal_mode: 'manual' | 'auto' | 'external'
  owner_id: string | null
  owner: string | null
  status: 'active' | 'pending' | 'expired' | 'transferred'
  notes: string
  review_state: 'unreviewed' | 'current' | 'stale' | 'conflict'
  observed_expiration_date: string | null
  last_reviewed_at: string | null
  monitoring_enabled: boolean
  monitor_state: 'never' | 'queued' | 'running' | 'current' | 'failed'
  monitor_error_code: string
  last_monitor_at: string | null
  next_monitor_at: string
  created_at: string
}

export type DomainMonitorRun = {
  id: string
  trigger: 'manual' | 'scheduled'
  state: 'pending' | 'processing' | 'succeeded' | 'failed'
  error_code: string
  rdap_source: string
  observed_expiration_date: string | null
  observed_registrar: string
  dns_source: string
  dnssec_validated: boolean | null
  dns_record_count: number
  created_at: string
  finished_at: string | null
}

export type DomainMonitorAlert = {
  id: string
  kind: 'expiration_due' | 'expiration_changed' | 'dns_changed' | 'collection_failed'
  observed_expiration_date: string | null
  prior_expiration_date: string | null
  created_at: string
}

export type DomainMonitoring = {
  domain: RegisteredDomain
  runs: DomainMonitorRun[]
  alerts: DomainMonitorAlert[]
  hostnames: { id: string; name: string }[]
}

export type CertificateEndpoint = {
  id: string
  domain_id: string
  hostname_id: string | null
  target_name: string
  protocol: 'https' | 'smtps' | 'imaps' | 'pop3s'
  port: number
  monitor_state: RegisteredDomain['monitor_state']
  monitor_error_code: string
  last_monitor_at: string | null
  next_monitor_at: string
  current_leaf_sha256: string
  current_not_after: string | null
  current_hostname_valid: boolean | null
  current_trust_valid: boolean | null
}

export type CertificateMonitorRun = {
  id: string
  trigger: 'manual' | 'scheduled'
  state: DomainMonitorRun['state']
  error_code: string
  leaf_sha256: string
  chain_sha256: string
  chain_length: number
  subject_common_name: string
  issuer_common_name: string
  san_count: number
  not_before: string | null
  not_after: string | null
  hostname_valid: boolean | null
  trust_valid: boolean | null
  tls_version: string
  cipher_name: string
  created_at: string
  finished_at: string | null
}

export type CertificateMonitoring = {
  endpoint: CertificateEndpoint
  runs: CertificateMonitorRun[]
  alerts: { id: string; kind: string; observed_not_after: string | null; prior_not_after: string | null; created_at: string }[]
}

export type DomainDraft = Pick<RegisteredDomain, 'name' | 'registrar_id' | 'registration_date' | 'expiration_date' | 'renewal_mode' | 'owner_id' | 'status' | 'notes'>

export interface DomainsClient {
  list(workspace: WorkspaceContext | null, signal?: AbortSignal): Promise<RegisteredDomain[]>
  create(workspace: WorkspaceContext | null, draft: DomainDraft): Promise<RegisteredDomain>
  monitoring(workspace: WorkspaceContext | null, domainId: string, signal?: AbortSignal): Promise<DomainMonitoring>
  scan(workspace: WorkspaceContext | null, domainId: string): Promise<DomainMonitorRun>
  listCertificates(workspace: WorkspaceContext | null, domainId: string): Promise<CertificateEndpoint[]>
  createCertificate(workspace: WorkspaceContext | null, domainId: string, protocol: CertificateEndpoint['protocol'], hostnameId: string | null): Promise<CertificateEndpoint>
  certificateMonitoring(workspace: WorkspaceContext | null, domainId: string, endpointId: string): Promise<CertificateMonitoring>
  scanCertificate(workspace: WorkspaceContext | null, domainId: string, endpointId: string): Promise<CertificateMonitorRun>
}

function path(workspace: WorkspaceContext | null) {
  return workspace
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/domains`
    : '/api/v1/workspaces/msp/domains'
}

function monitoringPath(workspace: WorkspaceContext | null, domainId: string) {
  return `${path(workspace)}/${encodeURIComponent(domainId)}/monitoring`
}

function certificatesPath(workspace: WorkspaceContext | null, domainId: string) {
  return `${path(workspace)}/${encodeURIComponent(domainId)}/certificates`
}

function certificateMonitoringPath(workspace: WorkspaceContext | null, domainId: string, endpointId: string) {
  return `${certificatesPath(workspace, domainId)}/${encodeURIComponent(endpointId)}/monitoring`
}

function csrfToken() {
  return document.cookie.split('; ').find((value) => value.startsWith('csrftoken='))?.split('=')[1] ?? ''
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string; error?: { message?: string } }
    throw new Error(body.error?.message ?? body.detail ?? 'The domain request failed.')
  }
  return response.json() as Promise<T>
}

export const browserDomainsClient: DomainsClient = {
  async list(workspace, signal) {
    return parse(await fetch(path(workspace), { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal }))
  },
  async create(workspace, draft) {
    await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    return parse(await fetch(path(workspace), {
      method: 'POST', credentials: 'same-origin',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify(draft),
    }))
  },
  async monitoring(workspace, domainId, signal) {
    return parse(await fetch(monitoringPath(workspace, domainId), {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
    }))
  },
  async scan(workspace, domainId) {
    await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    return parse(await fetch(monitoringPath(workspace, domainId), {
      method: 'POST', credentials: 'same-origin',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: '{}',
    }))
  },
  async listCertificates(workspace, domainId) {
    return parse(await fetch(certificatesPath(workspace, domainId), {
      credentials: 'same-origin', headers: { Accept: 'application/json' },
    }))
  },
  async createCertificate(workspace, domainId, protocol, hostnameId) {
    await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    return parse(await fetch(certificatesPath(workspace, domainId), {
      method: 'POST', credentials: 'same-origin',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify({ protocol, hostname_id: hostnameId }),
    }))
  },
  async certificateMonitoring(workspace, domainId, endpointId) {
    return parse(await fetch(certificateMonitoringPath(workspace, domainId, endpointId), {
      credentials: 'same-origin', headers: { Accept: 'application/json' },
    }))
  },
  async scanCertificate(workspace, domainId, endpointId) {
    await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    return parse(await fetch(certificateMonitoringPath(workspace, domainId, endpointId), {
      method: 'POST', credentials: 'same-origin',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: '{}',
    }))
  },
}
