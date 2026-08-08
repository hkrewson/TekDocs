import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import type { WorkspaceContext } from '../workspaces/api'
import { CustomFields } from './CustomFields'
import type { CustomFieldDefinition, CustomFieldsClient } from './api'

const workspace: WorkspaceContext = {
  kind: 'organization', id: '00000000-0000-4000-8000-000000000010', name: 'Acme Dental', classifications: ['client'], capabilities: ['overview', 'sites', 'custom_fields'],
  organization: { id: '00000000-0000-4000-8000-000000000010', name: 'Acme Dental', legal_name: '', website: '', classifications: ['client'], created_at: '', updated_at: '' },
}
const version = { id: '00000000-0000-4000-8000-000000000021', version: 1, label: 'Door code', description: 'Facilities entry code', required: false, field_type: 'text' as const, schema: { type: 'string' }, display_order: 1, created_at: '' }
const definition: CustomFieldDefinition = { id: '00000000-0000-4000-8000-000000000020', key: 'door_code', entity_type: 'site', owner: 'organization', organization_id: workspace.id, inherited: false, archived: false, current_version: version, versions: [version] }
const inherited: CustomFieldDefinition = { ...definition, id: '00000000-0000-4000-8000-000000000022', key: 'support_tier', owner: 'msp', organization_id: null, inherited: true, current_version: { ...version, id: '00000000-0000-4000-8000-000000000023', label: 'Support tier', field_type: 'choice', schema: { type: 'string', enum: ['Standard', 'Priority'] } }, versions: [{ ...version, id: '00000000-0000-4000-8000-000000000023', label: 'Support tier', field_type: 'choice', schema: { type: 'string', enum: ['Standard', 'Priority'] } }] }

function client(overrides: Partial<CustomFieldsClient> = {}): CustomFieldsClient {
  return {
    listDefinitions: vi.fn().mockResolvedValue({ results: [definition, inherited], count: 2 }),
    createDefinition: vi.fn().mockResolvedValue(definition),
    createVersion: vi.fn().mockResolvedValue({ definition, migration_impact: { total: 2, compatible: 1, incompatible: 1 } }),
    archiveDefinition: vi.fn().mockResolvedValue(undefined),
    listEntityFields: vi.fn(), setEntityValue: vi.fn(), clearEntityValue: vi.fn(),
    ...overrides,
  }
}

describe('CustomFields', () => {
  it('distinguishes organization fields from inherited MSP definitions', async () => {
    render(<CustomFields workspace={workspace} client={client()} />)
    expect(await screen.findByText('Door code')).toBeInTheDocument()
    expect(screen.getByText('Support tier')).toBeInTheDocument()
    expect(screen.getByText('Inherited from MSP')).toBeInTheDocument()
    expect(screen.getByText('Managed by MSP')).toBeInTheDocument()
  })

  it('creates a choice definition in the active organization', async () => {
    const user = userEvent.setup()
    const createDefinition = vi.fn().mockResolvedValue(definition)
    render(<CustomFields workspace={workspace} client={client({ createDefinition })} />)
    await screen.findByText('Door code')
    await user.click(screen.getByRole('button', { name: /New field/ }))
    await user.type(screen.getByLabelText('Label'), 'Support tier')
    await user.type(screen.getByLabelText('Stable key'), 'support tier')
    await user.selectOptions(screen.getByLabelText('Field type'), 'choice')
    await user.type(screen.getByLabelText(/Choices/), 'Standard\nPriority')
    await user.click(screen.getByRole('button', { name: 'Add field' }))

    expect(createDefinition).toHaveBeenCalledWith({ organizationId: workspace.id }, expect.objectContaining({ key: 'support_tier', field_type: 'choice', options: ['Standard', 'Priority'] }))
  })

  it('creates an immutable version with impact feedback and archives a definition', async () => {
    const user = userEvent.setup()
    const createVersion = vi.fn().mockResolvedValue({ definition, migration_impact: { total: 2, compatible: 1, incompatible: 1 } })
    const archiveDefinition = vi.fn().mockResolvedValue(undefined)
    render(<CustomFields workspace={workspace} client={client({ createVersion, archiveDefinition })} />)
    await screen.findByText('Door code')
    await user.click(screen.getByRole('button', { name: /New version/ }))
    await user.clear(screen.getByLabelText('Label'))
    await user.type(screen.getByLabelText('Label'), 'Entry code')
    await user.click(screen.getByRole('button', { name: 'Create version' }))
    expect(await screen.findByRole('status')).toHaveTextContent('1 require review')
    expect(createVersion).toHaveBeenCalledWith({ organizationId: workspace.id }, definition.id, expect.objectContaining({ label: 'Entry code' }))

    await user.click(screen.getByRole('button', { name: 'Archive' }))
    const dialog = screen.getByRole('alertdialog', { name: 'Archive Door code?' })
    await user.click(within(dialog).getByRole('button', { name: 'Archive' }))
    expect(archiveDefinition).toHaveBeenCalledWith({ organizationId: workspace.id }, definition.id)
  })
})
