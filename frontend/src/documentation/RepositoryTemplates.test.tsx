import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { vi } from 'vitest'
import { NavigationGuardProvider } from '../navigation/NavigationGuardProvider'
import { RepositoryTemplates, RepositoryTemplateLibrary } from './RepositoryTemplates'
import { browserRepositoryClient, type RepositorySource } from './repositoryApi'
const source = { content_id: 'doc', source_blob: 'blob', accepted_commit: 'commit', indexed_commit: 'commit', title: 'Guide', markdown: 'Intro', source: '', path: 'docs/doc.md', kind: 'document' } satisfies RepositorySource
function mount(element: React.ReactNode) { render(<RouterProvider router={createMemoryRouter([{ path: '*', element: <NavigationGuardProvider>{element}</NavigationGuardProvider> }])} />) }
it('configures only saved source state with explicit section selection and preserves denied drafts', async () => {
  const user = userEvent.setup()
  const client = { ...browserRepositoryClient, template: vi.fn().mockResolvedValue({ role: 'source', read_only: false, source: { enabled: false, library_visible: false, selected_fragment_ids: [], fragments: [{ id: 'section', title: 'Steps', markdown: 'Do this' }] } }), templateAction: vi.fn().mockRejectedValue(new Error('Denied')) }
  mount(<RepositoryTemplates source={source} client={client} disabled={false} onSaved={vi.fn()} onEditingChange={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Template settings and updates' }))
  await user.click(await screen.findByLabelText('Use as a template'))
  await user.click(screen.getByLabelText('Steps'))
  await user.click(screen.getByRole('button', { name: 'Save template settings' }))
  await waitFor(() => expect(client.templateAction).toHaveBeenCalledWith('doc', { action: 'configure', base_commit: 'commit', base_blob: 'blob', enabled: true, library_visible: false, fragment_ids: ['section'] }, undefined))
  expect(await screen.findByRole('alert')).toHaveTextContent('Denied')
  expect(screen.getByLabelText('Steps')).toBeChecked()
})
it('enrolls with reviewed definition and independent, live and pinned section choices', async () => {
  const user = userEvent.setup(), onCreated = vi.fn()
  const client = { ...browserRepositoryClient, templates: vi.fn().mockResolvedValue({ results: [{ id: 'template', title: 'Runbook', definition_sha256: 'hash', sections: [{ id: 'one', title: 'Steps', markdown: 'Text' }, { id: 'two', title: 'Policy', markdown: 'Fixed' }] }], count: 1, page: 1, page_size: 25, has_more: false }), enrollTemplate: vi.fn().mockResolvedValue(source) }
  mount(<RepositoryTemplateLibrary organizationId="client" workspaceName="Client" client={client} onCreated={onCreated} />)
  await user.click(await screen.findByRole('button', { name: 'Use Git-backed template' }))
  await user.selectOptions(screen.getByLabelText('Behavior for Steps'), 'live')
  await user.selectOptions(screen.getByLabelText('Behavior for Policy'), 'pinned')
  await user.click(screen.getByRole('button', { name: 'Create Git-backed document' }))
  await waitFor(() => expect(client.enrollTemplate).toHaveBeenCalledWith('client', { source_content_id: 'template', definition_sha256: 'hash', title: 'Client — Runbook', rules: { one: 'live', two: 'pinned' } }))
  expect(onCreated).toHaveBeenCalledWith(source)
})
const enrolled = { role: 'enrolled', read_only: false, enrollment: { source_title: 'Runbook', applied_revision_id: 'old', available_revision_id: 'new', expected_base: 'review-commit', expected_blob: 'review-blob', can_apply: true, changes: [{ id: 'section', title: 'Policy', mode: 'pinned', state: 'updated', markdown: 'Reviewed policy' }] } }
it('applies the exact reviewed revision and detaches only a clean review', async () => {
  const user = userEvent.setup(), onSaved = vi.fn()
  const client = { ...browserRepositoryClient, template: vi.fn().mockResolvedValue(enrolled), templateAction: vi.fn().mockResolvedValue(source) }
  mount(<RepositoryTemplates source={source} organizationId="client" client={client} disabled={false} onSaved={onSaved} onEditingChange={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Template settings and updates' }))
  await user.selectOptions(await screen.findByLabelText('Behavior for Policy'), 'pinned')
  expect(screen.getByRole('button', { name: 'Make Policy a local copy' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Apply reviewed update' }))
  await waitFor(() => expect(client.templateAction).toHaveBeenCalledWith('doc', { action: 'apply', base_commit: 'review-commit', base_blob: 'review-blob', expected_applied_revision_id: 'old', expected_available_revision_id: 'new', rules: { section: 'pinned' } }, 'client'))
  expect(onSaved).toHaveBeenCalledWith(source)
  await user.click(screen.getByRole('button', { name: 'Template settings and updates' }))
  await user.click(await screen.findByRole('button', { name: 'Make Policy a local copy' }))
  expect(client.templateAction).toHaveBeenLastCalledWith('doc', { action: 'detach', section_id: 'section', base_commit: 'review-commit', base_blob: 'review-blob', expected_applied_revision_id: 'old', expected_available_revision_id: 'new' }, 'client')
})
it('requires an explicit keep decision for removed and conflicting sections', async () => {
  const user = userEvent.setup()
  const client = { ...browserRepositoryClient, template: vi.fn().mockResolvedValue({ ...enrolled, enrollment: { ...enrolled.enrollment, changes: [{ id: 'section', title: 'Policy', mode: 'copy', state: 'removed', markdown: 'Local policy' }] } }), templateAction: vi.fn() }
  mount(<RepositoryTemplates source={source} client={client} disabled={false} onSaved={vi.fn()} onEditingChange={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Template settings and updates' }))
  expect(await screen.findByRole('button', { name: 'Apply reviewed update' })).toBeDisabled()
  await user.click(screen.getByLabelText('Keep local text'))
  expect(screen.getByRole('button', { name: 'Apply reviewed update' })).toBeEnabled()
  expect(client.templateAction).not.toHaveBeenCalled()
})
it('disables all mutations when the server returns read-only permission', async () => {
  const user = userEvent.setup()
  const client = { ...browserRepositoryClient, template: vi.fn().mockResolvedValue({ ...enrolled, read_only: true }), templateAction: vi.fn() }
  mount(<RepositoryTemplates source={source} client={client} disabled={false} onSaved={vi.fn()} onEditingChange={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Template settings and updates' }))
  expect(await screen.findByLabelText('Behavior for Policy')).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Apply reviewed update' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Make Policy a local copy' })).toBeDisabled()
  expect(client.templateAction).not.toHaveBeenCalled()
})
it('cannot open mutations over unsaved document changes', () => {
  const client = { ...browserRepositoryClient, template: vi.fn() }
  mount(<RepositoryTemplates source={source} client={client} disabled={true} onSaved={vi.fn()} onEditingChange={vi.fn()} />)
  expect(screen.getByRole('button', { name: 'Template settings and updates' })).toBeDisabled()
  expect(client.template).not.toHaveBeenCalled()
})
it('preserves reviewed choices on stale rejection and protects them when closing', async () => {
  const { RepositoryConflictError } = await import('./repositoryApi')
  const user = userEvent.setup(), onSaved = vi.fn()
  const client = { ...browserRepositoryClient, template: vi.fn().mockResolvedValue(enrolled), templateAction: vi.fn().mockRejectedValue(new RepositoryConflictError({ reason: 'stale', base: null, current: null, proposed: null, base_commit: null, current_commit: null, current_blob: null })) }
  mount(<RepositoryTemplates source={source} client={client} disabled={false} onSaved={onSaved} onEditingChange={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Template settings and updates' }))
  await user.selectOptions(await screen.findByLabelText('Behavior for Policy'), 'live')
  await user.click(screen.getByRole('button', { name: 'Apply reviewed update' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('The saved source changed')
  expect(screen.getByLabelText('Behavior for Policy')).toHaveValue('live')
  expect(onSaved).not.toHaveBeenCalled()
  expect(client.templateAction).toHaveBeenCalledTimes(1)
  await user.click(screen.getByRole('button', { name: 'Close' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(screen.getByLabelText('Behavior for Policy')).toHaveValue('live')
})
it('uses exact native routes, reviewed identities and CSRF for every mutation', async () => {
  document.cookie = 'csrftoken=synthetic-unit-csrf'
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(new Response(JSON.stringify(source), { status: 200, headers: { 'Content-Type': 'application/json' } })))
  try {
    await browserRepositoryClient.template('doc/id', 'org/id')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/workspaces/organizations/org%2Fid/content-graph/authoring/doc%2Fid/template', expect.objectContaining({ credentials: 'same-origin' }))
    const action = { action: 'detach' as const, section_id: 'section', base_commit: 'commit', base_blob: 'blob', expected_applied_revision_id: 'old', expected_available_revision_id: 'new' }
    await browserRepositoryClient.templateAction('doc', action, 'org')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/workspaces/organizations/org/content-graph/authoring/doc/template', expect.objectContaining({ method: 'POST', body: JSON.stringify(action), headers: { 'Content-Type': 'application/json', 'X-CSRFToken': 'synthetic-unit-csrf' } }))
    await browserRepositoryClient.templates('org', 'space & word', 2)
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/workspaces/organizations/org/content-graph/templates?q=space+%26+word&page=2', expect.anything())
    const input = { source_content_id: 'source', definition_sha256: 'digest', title: 'New', rules: { section: 'pinned' as const } }
    await browserRepositoryClient.enrollTemplate('org', input)
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/workspaces/organizations/org/content-graph/template-enrollments', expect.objectContaining({ body: JSON.stringify(input), method: 'POST' }))
  } finally { fetchMock.mockRestore(); document.cookie = 'csrftoken=; Max-Age=0' }
})
it('shows unavailable approved sources without stale cached controls and can retry', async () => {
  const { RepositoryConflictError } = await import('./repositoryApi')
  const user = userEvent.setup()
  const conflict = new RepositoryConflictError({ reason: 'unavailable', base: null, current: null, proposed: null, base_commit: null, current_commit: null, current_blob: null })
  Object.assign(conflict.conflict, { detail: 'Approved native template is unavailable' })
  const client = { ...browserRepositoryClient, template: vi.fn().mockRejectedValueOnce(conflict).mockResolvedValue(enrolled), templateAction: vi.fn() }
  mount(<RepositoryTemplates source={source} client={client} disabled={false} onSaved={vi.fn()} onEditingChange={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Template settings and updates' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Approved native template is unavailable')
  expect(screen.queryByRole('button', { name: 'Apply reviewed update' })).not.toBeInTheDocument()
  expect(screen.queryByText('Reviewed policy')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Retry' }))
  expect(await screen.findByLabelText('Behavior for Policy')).toBeEnabled()
  expect(client.templateAction).not.toHaveBeenCalled()
})
it('keeps a stale enrollment title and section choices until the user cancels', async () => {
  const user = userEvent.setup(), onCreated = vi.fn()
  const client = { ...browserRepositoryClient, templates: vi.fn().mockResolvedValue({ results: [{ id: 'template', title: 'Runbook', definition_sha256: 'hash', sections: [{ id: 'one', title: 'Steps', markdown: 'Text' }] }], count: 1, page: 1, page_size: 25, has_more: false }), enrollTemplate: vi.fn().mockRejectedValue(new Error('Template definition changed; review it again')) }
  mount(<RepositoryTemplateLibrary organizationId="client" workspaceName="Client" client={client} onCreated={onCreated} />)
  await user.click(await screen.findByRole('button', { name: 'Use Git-backed template' }))
  await user.selectOptions(screen.getByLabelText('Behavior for Steps'), 'pinned')
  await user.click(screen.getByRole('button', { name: 'Create Git-backed document' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Template definition changed; review it again')
  expect(screen.getByLabelText('Document title')).toHaveValue('Client — Runbook')
  expect(screen.getByLabelText('Behavior for Steps')).toHaveValue('pinned')
  expect(onCreated).not.toHaveBeenCalled()
  expect(client.enrollTemplate).toHaveBeenCalledTimes(1)
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  await user.click(await screen.findByRole('button', { name: 'Discard changes' }))
  await waitFor(() => expect(client.templates).toHaveBeenCalledTimes(2))
})
it('shows local copy edits beside the proposed source and requires an explicit decision', async () => {
  const user = userEvent.setup()
  const client = { ...browserRepositoryClient, template: vi.fn().mockResolvedValue({ ...enrolled, enrollment: { ...enrolled.enrollment, changes: [{ id: 'section', title: 'Policy', mode: 'copy', state: 'conflict', markdown: 'New source text', current_markdown: 'Independent client text' }] } }), templateAction: vi.fn().mockResolvedValue(source) }
  mount(<RepositoryTemplates source={source} client={client} disabled={false} onSaved={vi.fn()} onEditingChange={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Template settings and updates' }))
  expect(await screen.findByText('Independent client text')).toBeVisible()
  expect(screen.getByText('New source text')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Apply reviewed update' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Keep local text' }))
  await user.click(screen.getByRole('button', { name: 'Apply reviewed update' }))
  await waitFor(() => expect(client.templateAction).toHaveBeenCalledWith('doc', expect.objectContaining({ rules: { section: 'keep' } }), undefined))
})
