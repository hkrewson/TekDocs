import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { translate } from '../i18n/localization'
import type { ClientAsset, HardwareLifecycleEvent, InventoryClient } from './api'
import type { WorkspaceContext } from '../workspaces/api'
import { HardwareLifecycle } from './HardwareLifecycle'
import { HardwareAddresses } from './HardwareAddresses'
import { SoftwareInstallation } from './SoftwareInstallation'
import { AssetSpecifications } from './AssetSpecifications'
import { AssetRelationships } from './AssetRelationships'
import { RelationshipGraph } from '../relationships/RelationshipGraph'
import { browserRelationshipsClient } from '../relationships/api'

export function AssetFacts({ asset }: { asset: ClientAsset }) {
  const fields: Array<['serial' | 'tag' | 'status' | 'assignment' | 'site' | 'location' | 'warranty', string | null | undefined]> = [
    ['serial', asset.hardware?.serial_number], ['tag', asset.hardware?.asset_tag],
    ['status', (asset.hardware?.lifecycle_state ?? asset.software_installation?.status)?.replaceAll('_', ' ')],
    ['assignment', asset.hardware?.assignment.person_name],
    ['site', asset.hardware?.assignment.site_name ?? asset.software_installation?.site_name],
    ['location', asset.hardware?.assignment.location_name], ['warranty', asset.hardware?.warranty_ends_on],
  ]
  return <dl className="record-facts">{fields.filter(([key]) => asset.kind === 'hardware' || ['status', 'site'].includes(key ?? '')).map(([key, value]) => <div key={key}><dt>{translate(`collections.${key}`)}</dt><dd>{value || translate('collections.missing')}</dd></div>)}</dl>
}

export function AssetRecord({ asset, workspace, client, canManage, access, section, href, onChange }: {
  asset: ClientAsset; workspace: WorkspaceContext; client: InventoryClient; canManage: boolean
  access: { view: boolean; create: boolean; archive: boolean }; section: string
  href: (section: string) => string; onChange: (asset: ClientAsset) => void
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const tabs: Array<'overview' | 'specifications' | 'network' | 'installation' | 'related' | 'history'> = ['overview', 'specifications', asset.kind === 'hardware' ? 'network' : 'installation', ...(access.view ? ['related' as const] : []), 'history']
  const current = tabs.find((tab) => tab === section) ?? 'overview'
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus({ preventScroll: true }) }, [asset.id, current])
  const expired = asset.hardware?.warranty_ends_on && asset.hardware.warranty_ends_on < new Date().toISOString().slice(0, 10)
  const [graph, setGraph] = useState(false)
  return <article className="asset-record">
    <header className="asset-record-header"><h1 ref={heading} tabIndex={-1}>{asset.name}</h1><p>{asset.supplier_name} / {asset.product_name} / {asset.model_name}</p></header>
    <nav className="record-sections" aria-label={translate('collections.sections')}>{tabs.map((tab) => <Link key={tab} to={href(tab)} state={location.state as unknown} aria-current={current === tab ? 'page' : undefined}>{translate(`collections.${tab}`)}</Link>)}</nav>
    <label className="record-sections-mobile">{translate('collections.sections')}<select aria-label={translate('collections.sections')} value={current} onChange={(event) => { void navigate(href(event.target.value), { state: location.state as unknown }) }}>{tabs.map((tab) => <option key={tab} value={tab}>{translate(`collections.${tab}`)}</option>)}</select></label>
    <section aria-label={translate(`collections.${current}`)}>
      {current === 'overview' && <>
        {expired && <p role="status">{translate('collections.warrantyWarning')}</p>}
        {asset.hardware?.lifecycle_state === 'disposed' && <p role="status">{translate('collections.disposedWarning')}</p>}
        {asset.kind === 'hardware' ? <HardwareLifecycle key={asset.id} asset={asset} workspace={workspace} client={client} canManage={canManage} showHistory={false} onChange={(hardware) => onChange({ ...asset, hardware })} /> : <AssetFacts asset={asset} />}
      </>}
      {current === 'specifications' && <AssetSpecifications key={asset.id} selected={asset} workspace={workspace} client={client} />}
      {current === 'network' && <HardwareAddresses key={asset.id} asset={asset} workspace={workspace} client={client} canManage={canManage} onChange={(mac_addresses) => onChange({ ...asset, mac_addresses })} />}
      {current === 'installation' && <SoftwareInstallation key={asset.id} asset={asset} workspace={workspace} client={client} canManage={canManage} onChange={(software_installation) => onChange({ ...asset, software_installation })} />}
      {current === 'history' && <AssetHistory key={asset.id} asset={asset} workspace={workspace} client={client} />}
      {current === 'related' && access.view && <><AssetRelationships key={asset.id} workspace={workspace} assetId={asset.id} assetName={asset.name} canCreate={access.create} canArchive={access.archive} /><button type="button" className="secondary-button" aria-expanded={graph} onClick={() => setGraph(!graph)}>{translate('collections.graph')}</button>{graph && <RelationshipGraph scope={workspace.kind === 'organization' ? { organizationId: workspace.id } : {}} family="asset" rootId={asset.id} client={browserRelationshipsClient} heading={`${asset.name} relationships`} />}</>}
    </section>
  </article>
}

function AssetHistory({ asset, workspace, client }: { asset: ClientAsset; workspace: WorkspaceContext; client: InventoryClient }) {
  const [history, setHistory] = useState<HardwareLifecycleEvent[] | null>(null)
  const [error, setError] = useState(false)
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let active = true
    if (asset.hardware) client.listHardwareLifecycle(workspace, asset.id).then((events) => { if (active) { setHistory(events); setError(false) } }).catch(() => { if (active) setError(true) })
    return () => { active = false }
  }, [asset.id, asset.hardware, client, workspace, reload])
  if (!asset.hardware) return <p>{translate('collections.historySoftware')}</p>
  if (error) return <p role="alert">{translate('inventory.historyLoadFailed')} <button type="button" onClick={() => { setError(false); setReload(reload + 1) }}>{translate('inventory.retryHistory')}</button></p>
  if (!history) return <p role="status">{translate('collections.historyLoading')}</p>
  return history.length ? <ol>{history.map((item) => <li key={item.id}><strong>{item.event_type.replaceAll('_', ' ')}</strong> {[item.person_name, item.location_name, item.site_name].filter(Boolean).join(' · ')} <time dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleString()}</time></li>)}</ol> : <p>{translate('collections.historyEmpty')}</p>
}
