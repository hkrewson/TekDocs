/// <reference types="vite/client" />
import { describe, expect, it } from 'vitest'

import { hardcodedButtonLabels } from './buttonLabels'

/**
 * The catalog requirement, made executable.
 *
 * `docs/LOCALIZATION.md` and `frontend/AGENTS.md` require interface copy to come
 * from the message catalog. This test is the control: every component surface must
 * be free of literal button labels. The former exception register reached zero in
 * the 0.9.0 copy closeout, so every component is checked directly.
 *
 * Adding a new literal anywhere fails. Parameterised labels use one complete
 * catalog message with named substitution rather than translated fragments.
 */
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
      .map(([path, source]) => ({ path, labels: hardcodedButtonLabels(source) }))
      .filter((entry) => entry.labels.length > 0)

    expect(offenders).toEqual([])
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
