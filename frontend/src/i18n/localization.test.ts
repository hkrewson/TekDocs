import { describe, expect, it } from 'vitest'

import { configureDocumentLocalization, formatDateTime, formatHour, formatInstantDate, formatInteger, formatPlainDate, resolveLocale, runtimeLocale, runtimeTimeZone, translate } from './localization'

describe('localization contract', () => {
  it('negotiates only a shipped catalog and fails safely on hostile hints', () => {
    expect(resolveLocale(['fr-CA', 'en-GB'])).toBe('en-US')
    expect(resolveLocale(['not_a_locale'])).toBe('en-US')
    expect(runtimeLocale()).toBe('en-US')
    expect(runtimeTimeZone()).toBeTruthy()
  })

  it('formats instants in an explicit IANA zone across daylight-saving boundaries', () => {
    expect(formatDateTime('2026-03-08T07:30:00Z', { locale: 'en-US', timeZone: 'America/Chicago' })).toContain('1:30 AM')
    expect(formatDateTime('2026-03-08T08:30:00Z', { locale: 'en-US', timeZone: 'America/Chicago' })).toContain('3:30 AM')
    expect(() => formatDateTime('2026-03-08T08:30:00')).toThrow(/offset/)
    expect(() => formatDateTime('not-a-dateZ')).toThrow(/invalid/)
    expect(formatInstantDate('2026-03-08T08:30:00Z', { locale: 'en-US', timeZone: 'UTC' })).toBe('Mar 8, 2026')
  })

  it('keeps date-only values calendar-stable and validates impossible dates', () => {
    expect(formatPlainDate('2026-01-02', 'en-US')).toBe('Jan 2, 2026')
    expect(() => formatPlainDate('2026-02-30')).toThrow(/invalid/)
  })

  it('centralizes messages, integer grouping, and hour labels', () => {
    expect(translate('pagination.range', { first: 51, last: 100, count: 125 })).toBe('51–100 of 125')
    expect(formatInteger(12500, 'en-US')).toBe('12,500')
    expect(formatHour(13, 'en-US')).toBe('1 PM')
    expect(() => formatHour(24)).toThrow(/between/)
    expect(translate('pagination.page')).toBe('Page {page}')
  })

  it('publishes the active language and direction to assistive technology', () => {
    configureDocumentLocalization('en-US')
    expect(document.documentElement).toHaveAttribute('lang', 'en-US')
    expect(document.documentElement).toHaveAttribute('dir', 'ltr')
  })
})
