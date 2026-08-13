import enUS from './en-US.json'

export const supportedLocales = ['en-US'] as const
export type SupportedLocale = (typeof supportedLocales)[number]
export type MessageId = keyof typeof enUS
type MessageValues = Record<string, string | number>

const instantPattern = /(Z|[+-]\d{2}:\d{2})$/

export function resolveLocale(requested: readonly string[] = []): SupportedLocale {
  for (const candidate of requested) {
    try {
      const locale = new Intl.Locale(candidate)
      if (locale.language.toLowerCase() === 'en') return 'en-US'
    } catch {
      // Invalid browser or caller locale hints never become application state.
    }
  }
  return 'en-US'
}

export function runtimeLocale(): SupportedLocale {
  return resolveLocale(typeof navigator === 'undefined' ? [] : navigator.languages)
}

export function runtimeTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

export function configureDocumentLocalization(locale = runtimeLocale()) {
  document.documentElement.lang = locale
  document.documentElement.dir = locale === 'en-US' ? 'ltr' : 'ltr'
}

export function translate(id: MessageId, values: MessageValues = {}, locale = runtimeLocale()): string {
  void locale // The selected catalog will use this when another locale ships.
  return enUS[id].replace(/\{([a-zA-Z0-9_]+)\}/g, (token, key: string) => key in values ? String(values[key]) : token)
}

function instant(value: string | Date): Date {
  if (typeof value === 'string' && !instantPattern.test(value)) throw new RangeError('Timestamp must include a UTC or numeric offset.')
  const parsed = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(parsed.valueOf())) throw new RangeError('Timestamp is invalid.')
  return parsed
}

export function formatDateTime(value: string | Date, options: { locale?: SupportedLocale; timeZone?: string } = {}): string {
  return new Intl.DateTimeFormat(options.locale ?? runtimeLocale(), {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: options.timeZone,
  }).format(instant(value))
}

export function formatInstantDate(value: string | Date, options: { locale?: SupportedLocale; timeZone?: string } = {}): string {
  return new Intl.DateTimeFormat(options.locale ?? runtimeLocale(), {
    dateStyle: 'medium',
    timeZone: options.timeZone,
  }).format(instant(value))
}

export function formatPlainDate(value: string, locale = runtimeLocale()): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new RangeError('Plain date must use YYYY-MM-DD.')
  const [year, month, day] = value.split('-').map(Number)
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1 || parsed.getUTCDate() !== day) throw new RangeError('Plain date is invalid.')
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' }).format(parsed)
}

export function formatHour(hour: number, locale = runtimeLocale()): string {
  if (!Number.isInteger(hour) || hour < 0 || hour > 23) throw new RangeError('Hour must be between 0 and 23.')
  return new Intl.DateTimeFormat(locale, { hour: 'numeric', timeZone: 'UTC' }).format(new Date(Date.UTC(2000, 0, 1, hour)))
}

export function formatInteger(value: number, locale = runtimeLocale()): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value)
}
