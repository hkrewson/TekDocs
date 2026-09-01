/* eslint-disable @typescript-eslint/unbound-method */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { WorkspaceContext } from '../workspaces/api'
import { Imports } from './Imports'
import type { ImportBatch, ImportsClient } from './importsApi'

const workspace: WorkspaceContext = {
  kind: 'organization', id: 'client-1', name: 'Acme Dental', classifications: ['client'],
  capabilities: ['overview', 'integrations'], organization: null,
}

const batch: ImportBatch = {
  id: 'batch-1', source_format: 'tekdocs_csv', schema_version: 1, source_filename: 'sites.csv',
  source_digest: 'a'.repeat(64), state: 'preview_ready', result_counts: { create: 1 }, last_error_code: '',
  created_at: '2026-08-31T12:00:00Z', expires_at: '2026-09-01T12:00:00Z', applied_at: null,
}

function importsClient(): ImportsClient {
  return {
    list: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 25, count: 0, has_more: false }),
    preview: vi.fn().mockResolvedValue(batch),
    rows: vi.fn().mockResolvedValue({
      results: [{ id: 'row-1', row_number: 2, record_type: 'sites', external_key: 'site-1', action: 'create', reason_code: '', local_entity_id: null }],
      page: 1, page_size: 100, count: 1, has_more: false,
    }),
    apply: vi.fn().mockResolvedValue({ ...batch, state: 'applied', applied_at: '2026-08-31T12:01:00Z' }),
    cancel: vi.fn(), reportUrl: vi.fn().mockReturnValue('/report'), templateUrl: vi.fn().mockReturnValue('/template'),
  }
}

describe('Imports', () => {
  it('previews without applying and requires a separate apply decision', async () => {
    const client = importsClient()
    const user = userEvent.setup()
    render(<Imports workspace={workspace} client={client} />)

    expect(await screen.findByText(/No import has been previewed/i)).toBeInTheDocument()
    const file = new File(['external_key,name\nsite-1,Main office\n'], 'sites.csv', { type: 'text/csv' })
    await user.upload(screen.getByLabelText('File'), file)
    await user.click(screen.getByRole('button', { name: 'Preview import' }))

    await waitFor(() => expect(client.preview).toHaveBeenCalledWith(workspace, file, 'tekdocs_csv', 'sites'))
    expect(client.apply).not.toHaveBeenCalled()
    expect(await screen.findByText('site-1')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Apply import' }))
    await waitFor(() => expect(client.apply).toHaveBeenCalledWith(workspace, batch, {}))
  })

  it('blocks a possible match until the operator confirms the exact record', async () => {
    const client = importsClient()
    vi.mocked(client.list).mockResolvedValue({ results: [batch], page: 1, page_size: 25, count: 1, has_more: false })
    vi.mocked(client.rows).mockResolvedValue({
      results: [{ id: 'row-2', row_number: 2, record_type: 'sites', external_key: 'site-2', action: 'conflict', reason_code: 'possible_exact_match', local_entity_id: 'entity-2' }],
      page: 1, page_size: 100, count: 1, has_more: false,
    })
    const user = userEvent.setup()
    render(<Imports workspace={workspace} client={client} />)

    await user.click(await screen.findByRole('button', { name: 'Review' }))
    const apply = await screen.findByRole('button', { name: 'Apply import' })
    expect(apply).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: 'Use existing record' }))
    expect(apply).toBeEnabled()
    await user.click(apply)
    await waitFor(() => expect(client.apply).toHaveBeenCalledWith(workspace, batch, { 'row-2': 'entity-2' }))
  })
})
