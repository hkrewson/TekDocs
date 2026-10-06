import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { vi } from 'vitest'
import { NavigationGuardProvider } from '../navigation/NavigationGuardProvider'
import { RepositoryContentPanel } from './RepositoryContentPanel'
import { RepositoryConflictError, type RepositoryClient, type RepositorySource } from './repositoryApi'

const commit = 'a'.repeat(40)
const blob = 'b'.repeat(40)
const initial: RepositorySource = {
  content_id: 'content-1', path: 'docs/guide.md', kind: 'document', title: 'Guide',
  markdown: 'First revision.\n', source: '---\ntitle: Guide\n---\nFirst revision.\n',
  source_blob: blob, accepted_commit: commit, indexed_commit: commit,
}

function setup(overrides: Partial<RepositoryClient> = {}) {
  const save = vi.fn().mockResolvedValue({ ...initial, markdown: 'Changed revision.\n', accepted_commit: 'c'.repeat(40), indexed_commit: 'c'.repeat(40) })
  const client = {
    list: vi.fn().mockResolvedValue({ results: [{ id: 'content-1', title: 'Guide', kind: 'document', path: 'docs/guide.md' }], accepted_commit: commit, indexed_commit: commit, count: 1, has_more: false }),
    source: vi.fn().mockResolvedValue(initial),
    save,
    ...overrides,
  }
  const onClose = vi.fn()
  const router = createMemoryRouter([{
    path: '*', element: <NavigationGuardProvider><RepositoryContentPanel client={client} onClose={onClose} /></NavigationGuardProvider>,
  }])
  render(<RouterProvider router={router} />)
  return { client, onClose, save }
}

it('preserves a dirty draft through navigation and sends exact base identities on save', async () => {
  const user = userEvent.setup()
  const { save, onClose } = setup()
  expect(screen.getByRole('heading', { name: 'Repository content' })).toHaveFocus()
  await user.click(await screen.findByRole('button', { name: /Guide/ }))
  const body = await screen.findByLabelText('Markdown body')
  await user.clear(body)
  await user.type(body, 'Changed revision.')
  await user.click(screen.getByRole('button', { name: 'Back to documentation' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(onClose).not.toHaveBeenCalled()
  expect(body).toHaveValue('Changed revision.')
  await user.click(screen.getByRole('button', { name: 'Save to Git' }))
  await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({
    operation: 'update', content_id: 'content-1', base_commit: commit, base_blob: blob,
    markdown: 'Changed revision.', title: undefined,
  }), undefined))
  expect(await screen.findByText('Saved as one accepted Git commit.')).toBeInTheDocument()
})

it('keeps a denied or conflicting draft and exposes all three versions for review', async () => {
  const user = userEvent.setup()
  const save = vi.fn()
    .mockRejectedValueOnce(new Error('Editing denied'))
    .mockRejectedValueOnce(new RepositoryConflictError({
      reason: 'changed', base: 'Base source', current: 'Current source', proposed: 'My source',
      base_commit: commit, current_commit: 'c'.repeat(40), current_blob: 'd'.repeat(40),
    }))
  setup({ save })
  await user.click(await screen.findByRole('button', { name: /Guide/ }))
  const body = await screen.findByLabelText('Markdown body')
  await user.type(body, ' Local change')
  await user.click(screen.getByRole('button', { name: 'Save to Git' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Editing denied')
  expect(body).toHaveValue('First revision.\n Local change')
  await user.click(screen.getByRole('button', { name: 'Save to Git' }))
  expect(await screen.findByText('Current source')).toBeInTheDocument()
  expect(screen.getByText('Base source')).toBeInTheDocument()
  expect(screen.getByText('My source')).toBeInTheDocument()
  expect(body).toHaveValue('First revision.\n Local change')
})

it('refreshes a new-file base after an unrelated repository advance without discarding its draft', async () => {
  const user = userEvent.setup()
  const advanced = 'c'.repeat(40)
  const list = vi.fn()
    .mockResolvedValueOnce({ results: [], accepted_commit: commit, indexed_commit: commit, count: 0, has_more: false })
    .mockResolvedValue({ results: [], accepted_commit: advanced, indexed_commit: advanced, count: 0, has_more: false })
  const save = vi.fn()
    .mockRejectedValueOnce(new RepositoryConflictError({
      reason: 'repository_changed', base: null, current: null, proposed: null,
      base_commit: commit, current_commit: advanced, current_blob: null,
    }))
    .mockResolvedValue({ ...initial, accepted_commit: advanced, indexed_commit: advanced })
  setup({ list, save })
  await screen.findByText('No repository content matches this search.')
  await user.click(screen.getByRole('button', { name: 'New Markdown file' }))
  await user.type(screen.getByRole('textbox', { name: 'Title' }), 'New guide')
  await user.type(screen.getByLabelText('Markdown body'), 'Keep this draft')
  await user.click(screen.getByRole('button', { name: 'Save to Git' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('The repository changed')
  await user.click(screen.getByRole('button', { name: 'Use current as base and review my draft' }))
  expect(screen.getByLabelText('Markdown body')).toHaveValue('Keep this draft')
  await user.click(screen.getByRole('button', { name: 'Save to Git' }))
  await waitFor(() => expect(save).toHaveBeenLastCalledWith(expect.objectContaining({ base_commit: advanced }), undefined))
})
