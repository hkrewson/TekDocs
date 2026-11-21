import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

import { RepositoryInsertPicker } from './RepositoryInsertPicker'
import type { RepositoryClient, RepositorySource } from './repositoryApi'

const source: RepositorySource = {
  content_id: 'current', path: 'docs/current.md', kind: 'document', title: 'Current document',
  markdown: '', source: '', source_blob: 'b'.repeat(40), accepted_commit: 'a'.repeat(40), indexed_commit: 'a'.repeat(40),
}

it('waits for a search before offering records and returns the selected result', async () => {
  const user = userEvent.setup()
  const target = { id: 'asset-1', title: 'Core switch', kind: 'entity' as const, entity_type: 'client_asset', fields: ['name'] }
  const keys = vi.fn().mockResolvedValue({
    source_blob: source.source_blob, accepted_commit: source.accepted_commit, read_only: false,
    key_bindings: {}, targets: [target], bound_targets: [], has_more: false, report: [], report_has_more: false,
  })
  const onChoose = vi.fn()
  render(<RepositoryInsertPicker mode="record" source={source} organizationId="org-1" client={{ keys } as unknown as RepositoryClient} onChoose={onChoose} onClose={vi.fn()} />)

  expect(keys).not.toHaveBeenCalled()
  expect(screen.getByText('Type to search this workspace.')).toBeVisible()
  await user.type(screen.getByRole('searchbox'), 'core')
  await waitFor(() => expect(keys).toHaveBeenCalledWith('current', 'org-1', 'core', [], expect.any(AbortSignal)))
  await user.click(await screen.findByRole('button', { name: 'Insert Core switch' }))
  expect(onChoose).toHaveBeenCalledWith(target, {})
})

it('excludes the open document and closes with Escape', async () => {
  const user = userEvent.setup()
  const list = vi.fn().mockResolvedValue({ results: [
    { id: 'current', path: source.path, kind: 'document', title: source.title },
    { id: 'other', path: 'docs/other.md', kind: 'document', title: 'Other document' },
    { id: 'fragment', path: 'fragments/one.md', kind: 'fragment', title: 'Reusable steps' },
  ], next_cursor: null })
  const onClose = vi.fn()
  render(<RepositoryInsertPicker mode="document" source={source} client={{ list } as unknown as RepositoryClient} onChoose={vi.fn()} onClose={onClose} />)

  await user.type(screen.getByRole('searchbox'), 'document')
  expect(await screen.findByRole('button', { name: 'Insert Other document' })).toBeVisible()
  expect(screen.queryByText('Current document')).not.toBeInTheDocument()
  expect(screen.queryByText('Reusable steps')).not.toBeInTheDocument()
  await user.keyboard('{Escape}')
  expect(onClose).toHaveBeenCalledTimes(1)
})
