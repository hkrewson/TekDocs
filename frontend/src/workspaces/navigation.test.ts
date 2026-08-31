import { describe, expect, it } from 'vitest'
import { mspWorkspacePath, organizationWorkspacePath, workspaceAreaFromPath } from './navigation'
import type { WorkspaceOption } from './api'

const supplier: WorkspaceOption = {
  id: '00000000-0000-4000-8000-000000000012',
  name: 'Northwind Supply',
  classifications: ['vendor', 'manufacturer'],
  capabilities: ['overview', 'people', 'documentation', 'files', 'products'],
}

describe('workspace navigation', () => {
  it('derives scope from the URL and preserves equivalent areas', () => {
    expect(workspaceAreaFromPath('/workspaces/organizations/id/documentation')).toBe('documentation')
    expect(workspaceAreaFromPath('/assets')).toBe('assets')
    expect(workspaceAreaFromPath('/workspaces/organizations/id/search')).toBe('search')
    expect(organizationWorkspacePath(supplier, 'documentation')).toBe(`/workspaces/organizations/${supplier.id}/documentation`)
    expect(organizationWorkspacePath(supplier, 'search')).toBe(`/workspaces/organizations/${supplier.id}/search`)
    expect(mspWorkspacePath('documentation')).toBe('/documentation')
    expect(mspWorkspacePath('invoices')).toBe('/invoices')
    expect(workspaceAreaFromPath('/accounting')).toBe('invoices')
  })

  it('falls back to overview when the destination lacks the current area', () => {
    expect(organizationWorkspacePath(supplier, 'networks')).toBe(`/workspaces/organizations/${supplier.id}/overview`)
    expect(mspWorkspacePath('products')).toBe('/products')
  })
})
