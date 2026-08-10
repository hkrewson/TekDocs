import { useEffect, useState } from 'react'
import type { WorkspaceContext } from '../workspaces/api'
import type { DerivedVendor, InventoryClient } from './api'

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
  return <><header className="page-header"><div><h1>Vendors</h1><p>Suppliers derived from this client’s retained asset provenance.</p></div></header><section className="content-section">{phase === 'loading' && <p role="status">Loading client vendors…</p>}{phase === 'error' && <div className="workspace-error" role="alert"><h2>Vendors unavailable</h2><p>The derived supplier list could not be loaded.</p></div>}{phase === 'ready' && (vendors.length === 0 ? <p className="empty-state">Vendors appear here after a supplier product is used to create a client asset.</p> : <ul className="vendor-list">{vendors.map((vendor) => <li key={vendor.id}><div><strong>{vendor.name}</strong><span>{vendor.classifications.join(' · ')}</span></div><div><span>{vendor.asset_count} {vendor.asset_count === 1 ? 'asset' : 'assets'}</span>{vendor.website && <a href={vendor.website} rel="noreferrer" target="_blank">Website</a>}</div></li>)}</ul>)}</section></>
}
