import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ApplicationRouter } from '../navigation/ApplicationRouter'
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

function renderTaxonomies(api: TaxonomiesClient, path = '/taxonomies') {
  return render(<ApplicationRouter initialPath={path}><Taxonomies client={api} /></ApplicationRouter>)
}

describe('Taxonomies', () => {
  it('lists taxonomies and previews exact tag matches', async () => {
    const api = client()
    renderTaxonomies(api)
    expect(await screen.findByText('Technology')).toBeVisible()
    expect(screen.getByText('Technology').closest('li')).toHaveTextContent('2 documents · 1 templates')
    await userEvent.click(screen.getByRole('button', { name: 'Match existing tags' }))
    await userEvent.click(screen.getByRole('button', { name: 'Preview matches' }))
    expect(await screen.findByText('1 matched · 1 unmatched · 0 ambiguous')).toBeVisible()
    const migrationRow = screen.getByText('Recovery').closest('li')
    expect(migrationRow).toHaveTextContent('Azure AD')
    expect(migrationRow).toHaveTextContent('Entra ID')
  })

  it('creates a taxonomy with a plain term editor', async () => {
    const api = client()
    renderTaxonomies(api)
    await screen.findByText('Technology')
    await userEvent.click(screen.getByRole('button', { name: 'New taxonomy' }))
    await userEvent.type(screen.getByLabelText('Taxonomy key'), 'service-tier')
    const nameInputs = screen.getAllByLabelText('Name')
    await userEvent.type(nameInputs[0], 'Service tier')
    await userEvent.type(screen.getByLabelText('Label'), 'Gold')
    await userEvent.type(screen.getByLabelText('Term key'), 'gold')
    await userEvent.click(screen.getByRole('button', { name: 'Save taxonomy' }))
    await waitFor(() => expect(createTaxonomy).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'New taxonomy' })).not.toBeInTheDocument())
  })

  it('reorders a revised taxonomy and archives it after an in-page confirmation', async () => {
    const api = client()
    renderTaxonomies(api)
    await screen.findByText('Technology')

    await userEvent.click(screen.getByRole('button', { name: 'New version' }))
    await userEvent.click(screen.getByRole('button', { name: 'Add term' }))
    const termKeys = screen.getAllByLabelText('Term key')
    await userEvent.type(termKeys[termKeys.length - 1], 'intune')
    await userEvent.type(screen.getAllByLabelText('Label').at(-1)!, 'Intune')
    await userEvent.click(screen.getAllByRole('button', { name: 'Move up' }).at(-1)!)
    await userEvent.click(screen.getByRole('button', { name: 'Save taxonomy' }))
    await waitFor(() => expect(reviseTaxonomy).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: 'Archive' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Existing documents and published copies will keep their current terms.')
    await userEvent.click(screen.getByRole('alertdialog').querySelector('.danger-button')!)
    await waitFor(() => expect(archiveTaxonomy).toHaveBeenCalled())
  })

  it('restores URL filters and protects an edited taxonomy version', async () => {
    const api = client()
    const user = userEvent.setup()
    renderTaxonomies(api, `/taxonomies?q=tech&binding=document_tags&taxonomy=${taxonomy.id}`)
    expect(await screen.findByDisplayValue('tech')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Document tags ×' })).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    await user.clear(screen.getAllByLabelText('Name')[0])
    await user.type(screen.getAllByLabelText('Name')[0], 'Changed taxonomy')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(await screen.findByRole('heading', { name: 'Unsaved changes' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(screen.getByRole('dialog', { name: 'New version of Technology' })).toBeInTheDocument()
  })
})
