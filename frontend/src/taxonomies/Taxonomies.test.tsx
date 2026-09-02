import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { TaxonomiesClient, Taxonomy } from './api'
import { Taxonomies } from './Taxonomies'

const taxonomy: Taxonomy = {
  id: '10000000-0000-4000-8000-000000000001',
  key: 'technology',
  binding: 'document_tags',
  archived: false,
  current_version: {
    id: '10000000-0000-4000-8000-000000000002', version: 1, label: 'Technology', description: 'Products and platforms.', allow_local_terms: false, created_at: '2026-09-01T00:00:00Z',
    terms: [{ id: '10000000-0000-4000-8000-000000000003', stable_key: 'entra-id', label: 'Entra ID', description: 'Identity platform.', parent_key: '', aliases: ['Azure AD'], status: 'active', replacement_key: '', sort_order: 0 }],
  },
  versions: [{ id: '10000000-0000-4000-8000-000000000002', version: 1, label: 'Technology', created_at: '2026-09-01T00:00:00Z' }],
  impact: { documents: 2, templates: 1 },
}

let createTaxonomy = vi.fn()
let reviseTaxonomy = vi.fn()
let archiveTaxonomy = vi.fn()

function client(): TaxonomiesClient {
  createTaxonomy = vi.fn().mockResolvedValue(taxonomy)
  reviseTaxonomy = vi.fn().mockResolvedValue({ ...taxonomy, current_version: { ...taxonomy.current_version, version: 2 } })
  archiveTaxonomy = vi.fn().mockResolvedValue(undefined)
  return {
    list: vi.fn().mockResolvedValue({ results: [taxonomy], count: 1 }),
    create: createTaxonomy,
    revise: reviseTaxonomy,
    archive: archiveTaxonomy,
    migration: vi.fn().mockResolvedValue({ counts: { matched: 1, unmatched: 1, ambiguous: 0 }, rows: [{ document_id: '20000000-0000-4000-8000-000000000001', document_title: 'Recovery', tag: 'Azure AD', status: 'matched', term_id: taxonomy.current_version.terms[0].id, term_label: 'Entra ID' }] }),
  }
}

describe('Taxonomies', () => {
  it('lists governed vocabularies and previews exact legacy-tag matches', async () => {
    const api = client()
    render(<Taxonomies client={api} />)
    expect(await screen.findByText('Technology')).toBeVisible()
    expect(screen.getByText('2 documents · 1 templates')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Preview migration' }))
    expect(await screen.findByText('1 matched · 1 unmatched · 0 ambiguous')).toBeVisible()
    expect(screen.getByText('Azure AD')).toBeVisible()
    expect(screen.getByText('Entra ID')).toBeVisible()
  })

  it('creates a taxonomy with a plain term editor', async () => {
    const api = client()
    render(<Taxonomies client={api} />)
    await screen.findByText('Technology')
    await userEvent.click(screen.getByRole('button', { name: 'New taxonomy' }))
    await userEvent.type(screen.getAllByLabelText('Stable key')[0], 'service-tier')
    const nameInputs = screen.getAllByLabelText('Name')
    await userEvent.type(nameInputs[0], 'Service tier')
    await userEvent.type(screen.getByLabelText('Label'), 'Gold')
    const keyInputs = screen.getAllByLabelText('Stable key')
    await userEvent.type(keyInputs[1], 'gold')
    await userEvent.click(screen.getByRole('button', { name: 'Save taxonomy' }))
    await waitFor(() => expect(createTaxonomy).toHaveBeenCalled())
  })

  it('reorders a revised vocabulary and archives it after confirmation', async () => {
    const api = client()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<Taxonomies client={api} />)
    await screen.findByText('Technology')

    await userEvent.click(screen.getByRole('button', { name: 'New version' }))
    await userEvent.click(screen.getByRole('button', { name: 'Add term' }))
    const termKeys = screen.getAllByLabelText('Stable key')
    await userEvent.type(termKeys[termKeys.length - 1], 'intune')
    await userEvent.type(screen.getAllByLabelText('Label').at(-1)!, 'Intune')
    await userEvent.click(screen.getAllByRole('button', { name: 'Move up' }).at(-1)!)
    await userEvent.click(screen.getByRole('button', { name: 'Save taxonomy' }))
    await waitFor(() => expect(reviseTaxonomy).toHaveBeenCalled())

    await userEvent.click(screen.getByRole('button', { name: 'Archive' }))
    await waitFor(() => expect(archiveTaxonomy).toHaveBeenCalled())
    expect(confirm).toHaveBeenCalled()
  })
})
