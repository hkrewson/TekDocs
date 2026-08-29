import { useEffect, useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { Link } from 'react-router'

import { translate } from '../i18n/localization'
import type { WorkspaceClient, WorkspaceOption } from '../workspaces/api'
import type { OrganizationClassification } from '../organizations/api'

export function ProductCatalogs({ client }: { client: WorkspaceClient }) {
  const [suppliers, setSuppliers] = useState<WorkspaceOption[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    async function loadClassification(classification: OrganizationClassification) {
      const results: WorkspaceOption[] = []
      let page = 1
      let hasMore = true
      while (hasMore && page <= 1_000 && !controller.signal.aborted) {
        const response = await client.searchOrganizations('', page, controller.signal, classification)
        results.push(...response.results)
        hasMore = response.has_more
        page += 1
      }
      return results
    }
    Promise.all([
      loadClassification('vendor'),
      loadClassification('manufacturer'),
    ]).then(([vendors, manufacturers]) => {
      if (controller.signal.aborted) return
      const unique = new Map([...vendors, ...manufacturers].map((workspace) => [workspace.id, workspace]))
      setSuppliers([...unique.values()].sort((left, right) => left.name.localeCompare(right.name)))
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : translate('products.loadFailed'))
    })
    return () => controller.abort()
  }, [client])

  return <>
    <header className="page-header"><div><h1>{translate('products.heading')}</h1><p>{translate('products.intro')}</p></div></header>
    {error && <p className="form-error" role="alert">{error}</p>}
    <section className="content-section" aria-labelledby="supplier-catalogs-heading"><div className="section-heading"><div><h2 id="supplier-catalogs-heading">{translate('products.catalogs')}</h2><p>{translate('products.scope')}</p></div></div>{suppliers === null && !error ? <p role="status">{translate('products.loading')}</p> : suppliers?.length === 0 ? <p className="empty-state">{translate('products.empty')}</p> : <ul className="exposure-link-list">{suppliers?.map((supplier) => <li key={supplier.id}><span><strong>{supplier.name}</strong><small>{supplier.classifications.map((classification) => classification === 'manufacturer' ? translate('products.manufacturer') : classification === 'vendor' ? translate('products.vendor') : classification).join(' · ')}</small></span><Link className="secondary-button" to={`/workspaces/organizations/${encodeURIComponent(supplier.id)}/products`}>{translate('products.open')}<ExternalLink size={14} aria-hidden="true" /></Link></li>)}</ul>}</section>
  </>
}
