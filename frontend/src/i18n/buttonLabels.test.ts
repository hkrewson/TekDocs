/// <reference types="vite/client" />
import { describe, expect, it } from 'vitest'

import { hardcodedButtonLabels } from './buttonLabels'

/**
 * The catalog requirement, made executable.
 *
 * `docs/LOCALIZATION.md` and `frontend/AGENTS.md` require interface copy to come
 * from the message catalog. This test is the control: every component surface must
 * be free of literal button labels, and the only permitted exceptions are the ones
 * listed below with a recorded count.
 *
 * The list is an exception register, not a to-do list you may extend. Adding a new
 * literal anywhere fails. Adding one to an exempt file fails too, because each
 * entry pins an exact count. Entries are removed as their labels become
 * parameterised messages; nothing is ever added.
 *
 * Every remaining entry interleaves data with text, which `translate()` supports
 * through named substitution (`"{first}-{last} of {count}"`). They were left out of
 * the mechanical migration deliberately: turning `Edit <span>{person.full_name}</span>`
 * or `{count} · retained` into a catalog message is a copy decision, and assembling
 * a sentence from fragments is exactly what the message contract forbids.
 */
const PENDING_PARAMETERISED_LABELS: Record<string, number> = {
  'src/access-control/AccessCollectionsPanel.tsx': 1,
  'src/access-control/CustomRolesPanel.tsx': 1,
  'src/auth/AuthGate.tsx': 1,
  'src/compliance/Compliance.tsx': 1,
  'src/documentation/Documentation.tsx': 3,
  'src/inventory/Assets.tsx': 1,
  'src/inventory/Licenses.tsx': 1,
  'src/networks/NetworkAddressing.tsx': 1,
  'src/networks/NetworkEndpoints.tsx': 1,
  'src/organizations/Organizations.tsx': 2,
  'src/people/People.tsx': 2,
  'src/portal/ClientPortal.tsx': 1,
  'src/workspaces/WorkspaceSwitcher.tsx': 1,
}

const sources = Object.entries(
  import.meta.glob<string>('../**/*.tsx', { query: '?raw', import: 'default', eager: true }),
)
  .map(([path, source]) => [path.replace(/^\.\.\//, 'src/'), source] as const)
  .filter(([path]) => !path.endsWith('.test.tsx'))

describe('button label catalog coverage', () => {
  it('reads every component source', () => {
    expect(sources.length).toBeGreaterThan(40)
  })

  it('allows no hardcoded button label outside the exception register', () => {
    const offenders = sources
      .filter(([path]) => !(path in PENDING_PARAMETERISED_LABELS))
      .map(([path, source]) => ({ path, labels: hardcodedButtonLabels(source) }))
      .filter((entry) => entry.labels.length > 0)

    expect(offenders).toEqual([])
  })

  it('holds each exempt surface to its recorded count', () => {
    const grown = sources
      .filter(([path]) => path in PENDING_PARAMETERISED_LABELS)
      .map(([path, source]) => ({
        path,
        found: hardcodedButtonLabels(source).length,
        allowed: PENDING_PARAMETERISED_LABELS[path],
      }))
      .filter((entry) => entry.found > entry.allowed)

    expect(grown).toEqual([])
  })

  it('keeps the exception register free of resolved entries', () => {
    const byPath = new Map(sources)
    const stale = Object.keys(PENDING_PARAMETERISED_LABELS).filter((path) => {
      const source = byPath.get(path)
      return source === undefined || hardcodedButtonLabels(source).length === 0
    })

    expect(stale, 'remove these from PENDING_PARAMETERISED_LABELS').toEqual([])
  })

  it('recognises catalog-backed and literal labels', () => {
    const catalogBacked = "<button aria-label={translate('a.b')} onClick={() => go(a > b)}>"
      + '<Icon size={16} aria-hidden="true" /><span>{translate(\'a.b\')}</span></button>'
    expect(hardcodedButtonLabels(catalogBacked)).toEqual([])

    expect(hardcodedButtonLabels('<button type="button" onClick={() => save()}>Save site</button>'))
      .toEqual(['Save site'])

    // A handler containing `>` must not end the opening tag early.
    expect(hardcodedButtonLabels('<button onClick={() => setPage((value) => value + 1)}>Next</button>'))
      .toEqual(['Next'])

    // A self-closing button renders no children and owns no label.
    expect(hardcodedButtonLabels('<button className="backdrop" aria-label="Close" /><button>Real</button>'))
      .toEqual(['Real'])
  })
})
