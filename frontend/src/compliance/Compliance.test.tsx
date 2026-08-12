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
    evidence: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 100, count: 0, has_more: false }),
    createEvidence: vi.fn().mockResolvedValue({
      id: 'evidence-1', title: 'Access review', kind: 'note', summary: '', source_url: '', source_entity_id: null,
      source_entity_name: null, collection_start: null, collection_end: null, created_by: 'Owner', created_at: '2026-08-12T00:00:00Z',
      reviews: [], control_links: [],
    }),
    reviewEvidence: vi.fn().mockResolvedValue({
      id: 'evidence-review-1', status: 'collected', decision: 'Collected', note: '', reviewed_by: 'Owner', reviewed_at: '2026-08-12T00:00:00Z',
    }),
    linkEvidence: vi.fn().mockResolvedValue({
      id: 'evidence-link-1', assignment_id: 'assignment-1', control_id: 'control-1', control_revision: 1,
      linked_by: 'Owner', linked_at: '2026-08-12T00:00:00Z',
    }),
    risks: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 100, count: 0, has_more: false, owner_choices: [{ id: 'owner-1', display_name: 'Compliance Owner' }], summary: { total: 0, overdue: 0, by_status: {}, by_band: {} } }),
    createRisk: vi.fn().mockResolvedValue({
      id: 'risk-1', title: 'Recovery gap', description: '', assignment_id: null, control: null,
      likelihood: 4, impact: 4, score: 16, reporting_band: 'critical', status: 'open', treatment: 'mitigate', treatment_plan: '',
      owner_id: 'owner-1', owner: 'Compliance Owner', due_date: null, accepted_by: null, accepted_at: null, events: [],
    }),
    reviewRisk: vi.fn(),
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

  it('collects evidence and links it to an exact control assignment', async () => {
    const api = client()
    const user = userEvent.setup()
    vi.mocked(api.assignments).mockResolvedValue({
      results: [{
        id: 'assignment-1', framework_id: 'framework-1', control_id: 'control-1', control_identifier: 'AC-1',
        control_title: 'Asset inventory', control_revision: 1, applicability: 'applicable', implementation_status: 'implemented',
        owner_id: null, owner: null, review_due_date: null, reviews: [],
      }], owner_choices: [],
    })
    render(<Compliance workspace={null} client={api} />)

    await screen.findByRole('heading', { name: 'Security Baseline' })
    await user.click(screen.getByRole('button', { name: 'Add or link evidence' }))
    await user.type(screen.getByLabelText('Title'), 'Access review')
    await user.selectOptions(screen.getByLabelText('Kind'), 'url')
    await user.type(screen.getByLabelText('Source URL'), 'https://example.test/access-review')
    await user.type(screen.getByLabelText('Collection start'), '2026-07-01')
    await user.type(screen.getByLabelText('Collection end'), '2026-07-31')
    await user.selectOptions(screen.getByLabelText('Link to control'), 'assignment-1')
    await user.type(screen.getByLabelText('Collection decision'), 'Collected')
    await user.click(screen.getByRole('button', { name: 'Save evidence' }))

    await waitFor(() => expect(api.createEvidence).toHaveBeenCalledWith(null, expect.objectContaining({
      title: 'Access review', kind: 'url', source_url: 'https://example.test/access-review',
      collection_start: '2026-07-01', collection_end: '2026-07-31',
    })))
    expect(api.reviewEvidence).toHaveBeenCalledWith(null, 'evidence-1', expect.objectContaining({ status: 'collected', decision: 'Collected' }))
    expect(api.linkEvidence).toHaveBeenCalledWith(null, 'assignment-1', 'evidence-1')
  })

  it('records a scored risk treatment decision', async () => {
    const api = client()
    const user = userEvent.setup()
    render(<Compliance workspace={null} client={api} />)

    await screen.findByRole('heading', { name: 'Risk register' })
    await user.click(screen.getByRole('button', { name: 'Add risk' }))
    await user.type(screen.getByLabelText('Risk title'), 'Recovery gap')
    await user.clear(screen.getByLabelText('Likelihood (1–5)'))
    await user.type(screen.getByLabelText('Likelihood (1–5)'), '4')
    await user.clear(screen.getByLabelText('Impact (1–5)'))
    await user.type(screen.getByLabelText('Impact (1–5)'), '4')
    await user.selectOptions(screen.getByLabelText('Owner'), 'owner-1')
    await user.type(screen.getByLabelText('Decision'), 'Track and mitigate')
    await user.click(screen.getAllByRole('button', { name: 'Add risk' })[1])

    await waitFor(() => expect(api.createRisk).toHaveBeenCalledWith(null, expect.objectContaining({
      title: 'Recovery gap', likelihood: 4, impact: 4, owner_id: 'owner-1', decision: 'Track and mitigate',
    })))
  })

  it('records explicit acceptance while retaining the prior risk decision', async () => {
    const api = client()
    const user = userEvent.setup()
    const risk = {
      id: 'risk-1', title: 'Legacy platform', description: 'Unsupported.', assignment_id: null, control: null,
      likelihood: 4, impact: 5, score: 20, reporting_band: 'critical' as const, status: 'open' as const,
      treatment: 'mitigate' as const, treatment_plan: 'Replace.', owner_id: null, owner: null,
      due_date: '2026-08-01', accepted_by: null, accepted_at: null,
      events: [{ id: 'event-1', control_revision: null, likelihood: 4, impact: 5, status: 'open', treatment: 'mitigate', treatment_plan: 'Replace.', due_date: '2026-08-01', decision: 'Track', note: '', recorded_by: 'Owner', recorded_at: '2026-08-12T00:00:00Z' }],
    }
    vi.mocked(api.risks).mockResolvedValue({
      results: [risk], page: 1, page_size: 100, count: 1, has_more: false, owner_choices: [],
      summary: { total: 1, overdue: 1, by_status: { open: 1 }, by_band: { critical: 1, high: 0 } },
    })
    vi.mocked(api.reviewRisk).mockResolvedValue({ ...risk, status: 'accepted', treatment: 'accept', accepted_by: 'Owner', accepted_at: '2026-08-12T01:00:00Z' })
    render(<Compliance workspace={null} client={api} />)

    expect(await screen.findByText('Legacy platform')).toBeInTheDocument()
    expect(screen.getByText('20 · critical')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Review' }))
    await user.selectOptions(screen.getByLabelText('Status'), 'accepted')
    expect(screen.getByLabelText('Treatment')).toHaveValue('accept')
    expect(screen.getByText(/records you as the accepting actor/i)).toBeInTheDocument()
    await user.type(screen.getByLabelText('Decision'), 'Residual risk accepted')
    await user.click(screen.getByRole('button', { name: 'Save review' }))

    await waitFor(() => expect(api.reviewRisk).toHaveBeenCalledWith(null, 'risk-1', expect.objectContaining({
      status: 'accepted', treatment: 'accept', decision: 'Residual risk accepted',
    })))
  })
})
