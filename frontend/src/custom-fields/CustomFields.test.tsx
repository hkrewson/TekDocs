import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import type { WorkspaceContext } from '../workspaces/api'
import { CustomFields } from './CustomFields'
import type { CustomFieldDefinition, CustomFieldsClient } from './api'

const workspace: WorkspaceContext = {
  kind: 'organization', id: '00000000-0000-4000-8000-000000000010', name: 'Acme Dental', classifications: ['client'], capabilities: ['overview', 'sites', 'custom_fields'],
  organization: { id: '00000000-0000-4000-8000-000000000010', name: 'Acme Dental', legal_name: '', website: '', billing_contact_name: '', billing_email: '', billing_phone: '', billing_address_line_1: '', billing_address_line_2: '', billing_city: '', billing_region: '', billing_postal_code: '', billing_country_code: '', access_mode: 'assigned_only', classifications: ['client'], created_at: '', updated_at: '' },
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

function renderFields(api: CustomFieldsClient, path = `/workspaces/organizations/${workspace.id}/custom_fields`) {
  return render(<ApplicationRouter initialPath={path}><CustomFields workspace={workspace} client={api} /></ApplicationRouter>)
}

describe('CustomFields', () => {
  it('distinguishes organization fields from inherited MSP definitions', async () => {
    renderFields(client())
    expect(await screen.findByText('Door code')).toBeInTheDocument()
    expect(screen.getByText('Support tier')).toBeInTheDocument()
    expect(screen.getByText('Support tier').closest('li')).toHaveTextContent('From MSP workspace')
    expect(screen.getByText('Edit from MSP workspace')).toBeInTheDocument()
  })

  it('creates a choice definition in the active organization', async () => {
    const user = userEvent.setup()
    const createDefinition = vi.fn().mockResolvedValue(definition)
    renderFields(client({ createDefinition }))
    await screen.findByText('Door code')
    await user.click(screen.getByRole('button', { name: /New field/ }))
    await user.type(screen.getByLabelText('Label'), 'Support tier')
    await user.type(screen.getByLabelText(/Field key/), 'support tier')
    await user.selectOptions(screen.getByLabelText('Field type'), 'choice')
    await user.type(screen.getByLabelText(/Choices/), 'Standard\nPriority')
    await user.click(screen.getByRole('button', { name: 'Add field' }))

    expect(createDefinition).toHaveBeenCalledWith({ organizationId: workspace.id }, expect.objectContaining({ key: 'support_tier', field_type: 'choice', options: ['Standard', 'Priority'] }))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Add custom field' })).not.toBeInTheDocument())
  })

  it('creates an immutable version with impact feedback and archives a definition', async () => {
    const user = userEvent.setup()
    const createVersion = vi.fn().mockResolvedValue({ definition, migration_impact: { total: 2, compatible: 1, incompatible: 1 } })
    const archiveDefinition = vi.fn().mockResolvedValue(undefined)
    renderFields(client({ createVersion, archiveDefinition }))
    await screen.findByText('Door code')
    await user.click(screen.getByRole('button', { name: /New version/ }))
    await user.clear(screen.getByLabelText('Label'))
    await user.type(screen.getByLabelText('Label'), 'Entry code')
    await user.click(screen.getByRole('button', { name: 'Create version' }))
    expect(await screen.findByRole('status')).toHaveTextContent('1 needs review')
    expect(createVersion).toHaveBeenCalledWith({ organizationId: workspace.id }, definition.id, expect.objectContaining({ label: 'Entry code' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Archive Door code' }))
    const dialog = screen.getByRole('alertdialog', { name: 'Archive Door code?' })
    await user.click(within(dialog).getByRole('button', { name: 'Archive' }))
    expect(archiveDefinition).toHaveBeenCalledWith({ organizationId: workspace.id }, definition.id)
  })

  it('restores collection filters from the URL and guards a changed editor', async () => {
    const user = userEvent.setup()
    renderFields(client(), `/workspaces/organizations/${workspace.id}/custom_fields?q=door&entity_type=site&field=new`)
    expect(await screen.findByDisplayValue('door')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Site ×' })).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Label'), 'Changed')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(await screen.findByRole('heading', { name: 'Unsaved changes' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(screen.getByRole('dialog', { name: 'Add custom field' })).toBeInTheDocument()
  })
})
