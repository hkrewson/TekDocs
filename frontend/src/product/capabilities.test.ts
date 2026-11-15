import { authorizedTaskHubs, capabilityRegistry, navigationGroupRegistry, taskHubForCapability, taskHubRegistry, workspaceCapabilities } from './capabilities'

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

  it('uses the typed navigation groups as the only grouping authority', () => {
    const groupIds = navigationGroupRegistry.map(({ id }) => id)
    expect(new Set(groupIds).size).toBe(groupIds.length)
    expect(workspaceCapabilities.every((capability) => groupIds.includes(capabilityRegistry[capability].group))).toBe(true)
    expect(groupIds.every((group) => workspaceCapabilities.some((capability) => capabilityRegistry[capability].group === group))).toBe(true)
  })

  it('assigns every supported capability to exactly one task hub', () => {
    const assigned = taskHubRegistry.flatMap((hub) => [...hub.capabilities])
    expect(new Set(assigned)).toEqual(new Set(workspaceCapabilities))
    expect(assigned).toHaveLength(workspaceCapabilities.length)
    for (const capability of workspaceCapabilities) expect(taskHubForCapability(capability).capabilities).toContain(capability)
  })

  it('omits unavailable hubs and chooses the first authorized child deterministically', () => {
    const hubs = authorizedTaskHubs(['files', 'assets', 'domains'])
    expect(hubs.map(({ hub }) => hub.id)).toEqual(['knowledge', 'operations'])
    expect(hubs[0].children.map(({ capability }) => capability)).toEqual(['files'])
    expect(hubs[0].defaultDestination).toMatchObject({ capability: 'files', path: '/files' })
    expect(hubs[1].children.map(({ capability }) => capability)).toEqual(['assets', 'domains'])
    expect(hubs[1].defaultDestination.capability).toBe('assets')
  })

  it('keeps contextual and administrative routes out of primary hub children', () => {
    const hubs = authorizedTaskHubs(workspaceCapabilities)
    expect(hubs.find(({ hub }) => hub.id === 'home')?.children.map(({ capability }) => capability)).toEqual(['overview'])
    expect(hubs.find(({ hub }) => hub.id === 'assurance')?.children.map(({ capability }) => capability)).toEqual(['compliance'])
    expect(hubs.find(({ hub }) => hub.id === 'manage')?.children.map(({ capability }) => capability)).toEqual(['integrations', 'custom_fields', 'recycle_bin'])
    expect(taskHubForCapability('activity').id).toBe('home')
    expect(taskHubForCapability('taxonomies').id).toBe('manage')
  })
})
