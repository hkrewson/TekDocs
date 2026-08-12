/* eslint-disable @typescript-eslint/unbound-method */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { ComplianceClient, ComplianceFramework } from './api'
import { Compliance } from './Compliance'

const framework: ComplianceFramework = {
  id: 'framework-1',
  name: 'Security Baseline',
  revision_count: 1,
  can_manage: true,
  current_revision: {
    revision_number: 1,
    version_label: '2026.1',
    description: 'Initial catalog',
    source_url: '',
    content_digest: 'a'.repeat(64),
    created_at: '2026-08-12T00:00:00Z',
    created_by: 'Compliance Owner',
    entries: [{ position: 0, control: {
      control_id: 'control-1', revision_number: 1, identifier: 'AC-1', title: 'Asset inventory',
      description: 'Maintain an inventory.', guidance: '', content_digest: 'b'.repeat(64),
      created_at: '2026-08-12T00:00:00Z',
    } }],
  },
}

function client(): ComplianceClient {
  return {
    list: vi.fn().mockResolvedValue({ results: [framework], page: 1, page_size: 50, count: 1, has_more: false, can_manage: true }),
    create: vi.fn(),
    revisions: vi.fn().mockResolvedValue([framework.current_revision]),
    createVersion: vi.fn().mockResolvedValue({
      ...framework.current_revision, revision_number: 2, version_label: '2026.2', content_digest: 'c'.repeat(64),
    }),
    assignments: vi.fn().mockResolvedValue({
      results: [], owner_choices: [{ id: 'owner-1', display_name: 'Compliance Owner' }],
    }),
    reviewControl: vi.fn().mockResolvedValue({
      id: 'assignment-1', framework_id: 'framework-1', control_id: 'control-1',
      control_identifier: 'AC-1', control_title: 'Asset inventory', control_revision: 1,
      applicability: 'applicable', implementation_status: 'implemented', owner_id: null, owner: null,
      review_due_date: null, reviews: [{ id: 'review-1', decision: 'Verified', note: '', reviewed_by: 'Owner', reviewed_at: '2026-08-12T00:00:00Z' }],
    }),
  }
}

describe('Compliance', () => {
  it('loads the MSP catalog and creates a new immutable version from stable control identities', async () => {
    const api = client()
    const user = userEvent.setup()
    render(<Compliance workspace={null} client={api} />)

    expect(await screen.findByRole('heading', { name: 'Security Baseline' })).toBeInTheDocument()
    expect(screen.getByText('Asset inventory')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'New version' }))
    await user.type(screen.getByLabelText('Version label'), '2026.2')
    await user.type(screen.getByLabelText('Implementation guidance (Markdown)'), 'Review quarterly.')
    await user.click(screen.getByRole('button', { name: 'Create version' }))

    await waitFor(() => expect(api.createVersion).toHaveBeenCalledWith(null, 'framework-1', expect.objectContaining({
      version_label: '2026.2',
      controls: [expect.objectContaining({ control_id: 'control-1', identifier: 'AC-1' })],
    })))
    expect(await screen.findByRole('option', { name: /2026\.2 · revision 2/i })).toBeInTheDocument()
  })

  it('records an operational review against a stable control', async () => {
    const api = client()
    const user = userEvent.setup()
    render(<Compliance workspace={null} client={api} />)

    await screen.findByRole('heading', { name: 'Security Baseline' })
    await user.click(screen.getByRole('button', { name: 'Review control' }))
    await user.selectOptions(screen.getByLabelText('Applicability'), 'applicable')
    await user.selectOptions(screen.getByLabelText('Status'), 'implemented')
    await user.selectOptions(screen.getByLabelText('Owner'), 'owner-1')
    await user.type(screen.getByLabelText('Decision'), 'Verified')
    await user.click(screen.getByRole('button', { name: 'Save review' }))

    await waitFor(() => expect(api.reviewControl).toHaveBeenCalledWith(null, 'framework-1', 'control-1', expect.objectContaining({
      applicability: 'applicable', implementation_status: 'implemented', owner_id: 'owner-1', decision: 'Verified',
    })))
    expect(await screen.findByText(/applicable · implemented/i)).toBeInTheDocument()
  })
})
