import { capabilityRegistry, workspaceCapabilities } from './capabilities'

describe('product capability contract', () => {
  it('contains only supported, routable product capabilities', () => {
    expect(workspaceCapabilities).not.toContain('tickets')
    expect(workspaceCapabilities).not.toContain('accounting')
    expect(capabilityRegistry.invoices).toMatchObject({ label: 'Invoices', path: '/invoices', status: 'supported' })
    expect(workspaceCapabilities.every((capability) => capabilityRegistry[capability].status === 'supported')).toBe(true)
  })

  it('uses unique canonical paths', () => {
    const paths = workspaceCapabilities.map((capability) => capabilityRegistry[capability].path)
    expect(new Set(paths).size).toBe(paths.length)
  })
})
