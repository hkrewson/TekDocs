import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DocumentRemoteSourcePanel } from './DocumentRemoteSourcePanel'
import type { DocumentRemoteObservation, DocumentRemoteSource } from './api'

const source: DocumentRemoteSource = { id: 'source', url: 'https://example.invalid/guide', source_kind: 'markdown', enabled: false, check_interval_minutes: 180, next_check_at: '2026-10-31T00:00:00Z', last_checked_at: null, last_applied_observation_id: 'original' }
const observation: DocumentRemoteObservation = { id: 'changed', state: 'changed', status_code: 200, content_type: 'text/markdown', content_digest: 'a'.repeat(64), error_code: '', fetched_at: '2026-10-31T00:00:00Z', canonical_markdown: 'New instructions.', diff: 'Previous source baseline', apply_review: { fingerprint: 'b'.repeat(64), blocker: '', diff: 'Current document diff' } }

describe('monitored source review', () => {
  function panel(observations: DocumentRemoteObservation[], settingsDirty = false) {
    const apply = vi.fn()
    render(<DocumentRemoteSourcePanel busy={false} settingsDirty={settingsDirty} source={source} draft={source} observations={observations} onApplyObservation={apply} onCheck={vi.fn()} onClose={vi.fn()} onDraftChange={vi.fn()} onSave={vi.fn()} />)
    return apply
  }

  it('preserves local edits and directs the reviewer to manual integration', async () => {
    const apply = panel([{ ...observation, apply_review: { fingerprint: 'b'.repeat(64), blocker: 'local_edits_require_integration', diff: 'Current document diff' } }])
    expect(screen.getByRole('status')).toHaveTextContent('Local edits are preserved.')
    expect(screen.getByText('Current document diff')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Apply reviewed change' }))
    expect(apply).not.toHaveBeenCalled()
  })

  it('discloses live reuse and retained-version impact before applying', async () => {
    const apply = panel([observation])
    expect(screen.getByText('Applying this source also updates documents that follow this section. Pinned versions and signed publications stay unchanged.')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Apply reviewed change' }))
    expect(apply).toHaveBeenCalledWith(observation)
  })

  it('keeps an unapplied change reviewable when a later check is unchanged', async () => {
    const pending = { ...observation, state: 'unchanged' as const }
    const apply = panel([pending])
    expect(screen.getByText('Current document diff')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Apply reviewed change' }))
    expect(apply).toHaveBeenCalledWith(pending)
  })

  it('does not offer an unchanged source that matches the applied baseline', () => {
    panel([{ ...observation, state: 'unchanged', diff: '' }])
    expect(screen.getByText('No change')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Apply reviewed change' })).not.toBeInTheDocument()
  })

  it('requires source settings to be saved before check or apply', async () => {
    const apply = panel([observation], true)
    expect(screen.getByRole('button', { name: 'Check now' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Apply reviewed change' }))
    expect(apply).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Save source' })).toBeEnabled()
  })

  it('shows failed checks without presenting an unavailable apply review as an action', () => {
    panel([{ ...observation, id: 'failed', state: 'failed', canonical_markdown: '', diff: '', error_code: 'remote_connection_failed', apply_review: { fingerprint: '', blocker: 'source_review_unavailable', diff: '' } }])
    expect(screen.getByText('Check failed')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Apply reviewed change' })).not.toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
