import { useEffect, useState } from 'react'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { DerivedVendor, InventoryClient } from './api'

function classificationLabel(classification: string) {
  if (classification === 'vendor') return translate('products.vendor')
  if (classification === 'manufacturer') return translate('products.manufacturer')
  return classification
}

export function Vendors({ workspace, client }: { workspace: WorkspaceContext; client: InventoryClient }) {
  const [vendors, setVendors] = useState<DerivedVendor[]>([])
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  useEffect(() => {
    const controller = new AbortController()
    client.listVendors(workspace, controller.signal)
      .then((result) => { setVendors(result.results); setPhase('ready') })
      .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client, workspace])
  const intro = workspace.kind === 'msp' ? translate('vendors.introMsp') : translate('vendors.introClient')
  return <>
    <header className="page-header"><div><h1>{translate('vendors.heading')}</h1><p>{intro}</p></div></header>
    <section className="content-section">
      {phase === 'loading' && <p role="status">{translate('vendors.loading')}</p>}
      {phase === 'error' && <div className="workspace-error" role="alert"><h2>{translate('vendors.unavailable')}</h2><p>{translate('vendors.loadFailed')}</p></div>}
      {phase === 'ready' && (vendors.length === 0
        ? <p className="empty-state">{translate('vendors.empty')}</p>
        : <ul className="vendor-list">{vendors.map((vendor) => <li key={vendor.id}><div><strong>{vendor.name}</strong><span>{vendor.classifications.map(classificationLabel).join(' · ')}</span></div><div><span>{translate(vendor.asset_count === 1 ? 'vendors.assetCount' : 'vendors.assetCountPlural', { count: vendor.asset_count })}</span>{vendor.website && <a href={vendor.website} rel="noreferrer" target="_blank">{translate('vendors.website')}</a>}</div></li>)}</ul>)}
    </section>
  </>
}
