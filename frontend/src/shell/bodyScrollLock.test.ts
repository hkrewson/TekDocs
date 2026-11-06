import { afterEach, expect, it } from 'vitest'

import { lockBodyScroll } from './bodyScrollLock'

afterEach(() => document.body.removeAttribute('class'))

it('keeps scrolling locked until every overlapping overlay releases it', () => {
  const releaseFirst = lockBodyScroll()
  const releaseSecond = lockBodyScroll()

  expect(document.body).toHaveClass('tekdocs-scroll-locked')
  releaseFirst()
  expect(document.body).toHaveClass('tekdocs-scroll-locked')
  releaseSecond()
  expect(document.body).not.toHaveClass('tekdocs-scroll-locked')
})

it('makes release idempotent', () => {
  const release = lockBodyScroll()

  release()
  release()

  expect(document.body).not.toHaveClass('tekdocs-scroll-locked')
})
