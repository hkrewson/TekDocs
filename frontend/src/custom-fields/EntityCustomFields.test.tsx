import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { EntityCustomFields } from './EntityCustomFields'
import type { CustomFieldDefinition, CustomFieldsClient, EntityCustomFieldResult } from './api'

const entityId = '00000000-0000-4000-8000-000000000030'
const version = { id: '00000000-0000-4000-8000-000000000021', version: 2, label: 'Door code', description: 'Facilities entry code', required: false, field_type: 'text' as const, schema: { type: 'string' }, display_order: 1, created_at: '' }
const definition: CustomFieldDefinition = { id: '00000000-0000-4000-8000-000000000020', key: 'door_code', entity_type: 'site', owner: 'msp', organization_id: null, inherited: false, archived: false, current_version: version, versions: [version] }
const result: EntityCustomFieldResult = { entity_id: entityId, entity_type: 'site', fields: [{ definition, has_value: true, value: '4231', value_version_id: 'old', value_version: 1, is_current: false, valid_for_current: true }] }

function client(overrides: Partial<CustomFieldsClient> = {}): CustomFieldsClient {
  return {
    listDefinitions: vi.fn(), createDefinition: vi.fn(), createVersion: vi.fn(), archiveDefinition: vi.fn(),
    listEntityFields: vi.fn().mockResolvedValue(result),
    setEntityValue: vi.fn().mockResolvedValue({ ...result, fields: [{ ...result.fields[0], value: '9912', value_version: 2, is_current: true }] }),
    clearEntityValue: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

describe('EntityCustomFields', () => {
  it('reviews a historical value and saves it against the latest version', async () => {
    const user = userEvent.setup()
    const setEntityValue = vi.fn().mockResolvedValue({ ...result, fields: [{ ...result.fields[0], value: '9912', value_version: 2, is_current: true }] })
    render(<EntityCustomFields workspace={null} entityId={entityId} entityName="North Campus" onClose={vi.fn()} client={client({ setEntityValue })} />)
    expect(await screen.findByDisplayValue('4231')).toBeInTheDocument()
    expect(screen.getByText(/Stored with version 1/)).toBeInTheDocument()
    await user.clear(screen.getByLabelText('Door code'))
    await user.type(screen.getByLabelText('Door code'), '9912')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(setEntityValue).toHaveBeenCalledWith({}, entityId, definition.id, '9912')
  })

  it('clears a value and closes the editor', async () => {
    const user = userEvent.setup()
    const clearEntityValue = vi.fn().mockResolvedValue(undefined)
    const onClose = vi.fn()
    render(<EntityCustomFields workspace={null} entityId={entityId} entityName="North Campus" onClose={onClose} client={client({ clearEntityValue })} />)
    await screen.findByDisplayValue('4231')
    await user.click(screen.getByRole('button', { name: 'Clear' }))
    expect(clearEntityValue).toHaveBeenCalledWith({}, entityId, definition.id)
    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('uses an explicit empty state when no definition applies', async () => {
    render(<EntityCustomFields workspace={null} entityId={entityId} entityName="North Campus" onClose={vi.fn()} client={client({ listEntityFields: vi.fn().mockResolvedValue({ entity_id: entityId, entity_type: 'site', fields: [] }) })} />)
    expect(await screen.findByText(/No custom fields apply/)).toBeInTheDocument()
  })
})
