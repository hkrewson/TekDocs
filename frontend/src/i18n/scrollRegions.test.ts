/// <reference types="vite/client" />
import { describe, expect, it } from 'vitest'

/**
 * Horizontally scrollable tables must be operable by keyboard.
 *
 * A container with `overflow-x: auto` scrolls with a pointer or a trackpad, but a
 * keyboard user cannot reach it unless it is focusable, so any column past the
 * right edge is unreachable — WCAG 2.1.1. `tabindex="0"` makes the region
 * arrow-key scrollable; `role="region"` with an accessible name tells assistive
 * technology what it holds, which matters most on the narrow viewports where the
 * overflow actually happens.
 *
 * This is the control for that rule. A new scrollable table wrapper without the
 * three attributes fails here rather than shipping unreachable.
 */

/** Wrapper classes that carry `overflow-x: auto` in `styles.css`. */
const SCROLL_REGION_CLASSES = [
  'network-table-wrap',
  'people-table-wrap',
  'recycle-bin-table-wrap',
  'asset-csv-table-wrap',
  'table-scroll',
]

const sources = Object.entries(
  import.meta.glob<string>('../**/*.tsx', { query: '?raw', import: 'default', eager: true }),
)
  .map(([path, source]) => [path.replace(/^\.\.\//, 'src/'), source] as const)
  .filter(([path]) => !path.endsWith('.test.tsx'))

type Region = { path: string; tag: string }

function scrollRegions(path: string, source: string): Region[] {
  const found: Region[] = []
  for (const cls of SCROLL_REGION_CLASSES) {
    const pattern = new RegExp(`<div className="[^"]*\\b${cls}\\b[^"]*"[^>]*>`, 'g')
    for (const match of source.matchAll(pattern)) found.push({ path, tag: match[0] })
  }
  return found
}

const regions = sources.flatMap(([path, source]) => scrollRegions(path, source))

describe('scrollable table regions', () => {
  it('finds the scroll regions', () => {
    expect(regions.length).toBeGreaterThan(20)
  })

  it('makes every scroll region keyboard focusable and named', () => {
    const unreachable = regions
      .filter((region) => !(
        region.tag.includes('tabIndex={0}')
        && region.tag.includes('role="region"')
        && /aria-label=/.test(region.tag)
      ))
      .map((region) => `${region.path}: ${region.tag.slice(0, 90)}`)

    expect(unreachable).toEqual([])
  })

  it('names each region through the message catalog', () => {
    const literal = regions
      .filter((region) => /aria-label="/.test(region.tag))
      .map((region) => `${region.path}: ${region.tag.slice(0, 90)}`)

    expect(literal, 'use translate() for scroll region names').toEqual([])
  })
})
