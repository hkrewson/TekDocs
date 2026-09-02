import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type { AuthClient } from '../auth/api'
import { translate } from '../i18n/localization'
import { InvoiceRequestError } from './api'
import type { InvoiceClient, InvoiceDateComponent, InvoiceIssueSettings } from './api'

type SettingsClient = Pick<InvoiceClient, 'issueSettings' | 'saveIssueSettings'>
type ReauthenticationClient = Pick<AuthClient, 'reauthenticate'>

export function InvoiceSettings({ client, authClient }: { client: SettingsClient; authClient: ReauthenticationClient }) {
  const [value, setValue] = useState<InvoiceIssueSettings | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<'none' | 'saved' | 'error'>('none')
  const [errorMessage, setErrorMessage] = useState('')
  const [reauthenticationRequired, setReauthenticationRequired] = useState(false)
  const [password, setPassword] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    client.issueSettings(controller.signal)
      .then((settings) => { setValue(settings); setPhase('ready') })
      .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client])

  function currentPayload() {
    if (!value) return null
    const payload: Record<string, unknown> = { ...value }
    delete payload.configured
    delete payload.issue_ready
    delete payload.readiness_issues
    delete payload.country_choices
    return payload
  }

  async function saveSettings() {
    const payload = currentPayload()
    if (!payload) return
    setBusy(true)
    setMessage('none')
    setErrorMessage('')
    try {
      setValue(await client.saveIssueSettings(payload))
      setReauthenticationRequired(false)
      setMessage('saved')
    } catch (saveError) {
      if (saveError instanceof InvoiceRequestError && saveError.code === 'recent_authentication_required') {
        setReauthenticationRequired(true)
      } else {
        setErrorMessage(saveError instanceof Error ? saveError.message : translate('accounting.settingsFailed'))
      }
      setMessage('error')
    } finally {
      setBusy(false)
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    await saveSettings()
  }

  async function confirmPassword(event: FormEvent) {
    event.preventDefault()
    const submittedPassword = password
    setPassword('')
    setBusy(true)
    setMessage('none')
    setErrorMessage('')
    try {
      await authClient.reauthenticate(submittedPassword)
      setReauthenticationRequired(false)
      await saveSettings()
    } catch (confirmationError) {
      setMessage('error')
      setErrorMessage(
        confirmationError instanceof Error ? confirmationError.message : translate('accounting.reauthenticationFailed'),
      )
      setBusy(false)
    }
  }

  return <>
    <header className="page-header"><div><h1>{translate('accounting.issueSettings')}</h1><p>{translate('accounting.settingsScope')}</p></div></header>
    {phase === 'loading' && <section className="content-section" role="status">{translate('accounting.settingsLoading')}</section>}
    {phase === 'error' && <section className="content-section workspace-error" role="alert"><h2>{translate('accounting.settingsUnavailable')}</h2><p>{translate('accounting.settingsLoadFailed')}</p></section>}
    {phase === 'ready' && reauthenticationRequired && <form className="content-section invoice-reauth-form" onSubmit={(event) => { void confirmPassword(event) }}>
      <div><h2>{translate('accounting.confirmSave')}</h2><p>{translate('accounting.confirmSaveHelp')}</p></div>
      <label><span>{translate('accounting.currentPassword')}</span><input autoFocus required type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
      <button type="submit" className="primary-button" disabled={busy}>{busy ? translate('accounting.confirming') : translate('accounting.confirmAndSave')}</button>
      {message === 'error' && errorMessage && <div className="form-message error wide-field" role="alert">{errorMessage}</div>}
    </form>}
    {phase === 'ready' && value && <form className="content-section record-form invoice-settings-form" onSubmit={(event) => { void save(event) }}>
      {message === 'saved' && <div className="form-message success" role="status">{translate('accounting.settingsSaved')}</div>}
      {message === 'error' && !reauthenticationRequired && <div className="form-message error" role="alert">{errorMessage || translate('accounting.settingsFailed')}</div>}
      {!value.issue_ready && value.readiness_issues.length > 0 && <div className="form-message" role="status"><strong>{translate('accounting.settingsIncomplete')}</strong><ul>{value.readiness_issues.map((issue) => <li key={issue}>{issue}</li>)}</ul></div>}
      <div className="form-grid">
        <fieldset className="record-form-section wide-field"><legend>{translate('accounting.businessDetails')}</legend><div className="form-grid">
          <Field autoFocus label={translate('accounting.legalName')} value={value.legal_name} onChange={(legal_name) => setValue({ ...value, legal_name })} />
          <Field label={translate('accounting.billingEmail')} type="email" value={value.billing_email} onChange={(billing_email) => setValue({ ...value, billing_email })} />
          <Field label={translate('accounting.phone')} value={value.phone} required={false} onChange={(phone) => setValue({ ...value, phone })} />
          <Field label={translate('accounting.taxRegistration')} value={value.tax_registration} required={false} onChange={(tax_registration) => setValue({ ...value, tax_registration })} />
          <Field label={translate('accounting.addressLine1')} value={value.address_line_1} onChange={(address_line_1) => setValue({ ...value, address_line_1 })} />
          <Field label={translate('accounting.addressLine2')} value={value.address_line_2} required={false} onChange={(address_line_2) => setValue({ ...value, address_line_2 })} />
          <Field label={translate('accounting.city')} value={value.city} onChange={(city) => setValue({ ...value, city })} />
          <Field label={translate('accounting.region')} value={value.region} required={false} onChange={(region) => setValue({ ...value, region })} />
          <Field label={translate('accounting.postalCode')} value={value.postal_code} onChange={(postal_code) => setValue({ ...value, postal_code })} />
          <label><span>{translate('accounting.country')}</span><select required autoComplete="country" value={value.country_code} onChange={(event) => setValue({ ...value, country_code: event.target.value })}>
            <option value="">{translate('accounting.selectCountry')}</option>
            {value.country_choices.map((country) => <option key={country.value} value={country.value}>{country.label} — {country.value}</option>)}
          </select></label>
        </div></fieldset>
        <fieldset className="record-form-section wide-field"><legend>{translate('accounting.invoiceDefaults')}</legend><div className="form-grid">
          <Field label={translate('accounting.defaultCurrency')} value={value.default_currency} onChange={(default_currency) => setValue({ ...value, default_currency: default_currency.toUpperCase() })} />
          <Field label={translate('accounting.paymentTerms')} type="number" value={String(value.payment_terms_days)} onChange={(payment_terms_days) => setValue({ ...value, payment_terms_days: Number(payment_terms_days) })} />
        </div></fieldset>
        <fieldset className="record-form-section wide-field numbering-settings"><legend>{translate('accounting.invoiceNumbering')}</legend>
          <p className="field-help">{translate('accounting.numberingHelp')}</p>
          <div className="form-grid">
            <Field label={translate('accounting.invoicePrefix')} value={value.invoice_prefix} onChange={(invoice_prefix) => setValue({ ...value, invoice_prefix: invoice_prefix.toUpperCase() })} />
            <SelectField label={translate('accounting.dateComponent')} value={value.invoice_date_component} options={DATE_OPTIONS} onChange={(invoice_date_component) => setValue({ ...value, invoice_date_component: invoice_date_component as InvoiceDateComponent })} />
            <SelectField label={translate('accounting.separator')} value={value.invoice_separator} options={SEPARATOR_OPTIONS} onChange={(invoice_separator) => setValue({ ...value, invoice_separator: invoice_separator as InvoiceIssueSettings['invoice_separator'] })} />
            <SelectField label={translate('accounting.sequenceDigits')} value={String(value.invoice_sequence_digits)} options={DIGIT_OPTIONS} onChange={(invoice_sequence_digits) => setValue({ ...value, invoice_sequence_digits: Number(invoice_sequence_digits) })} />
            <SelectField label={translate('accounting.restartNumbering')} value={value.invoice_reset_period} options={RESET_OPTIONS} onChange={(invoice_reset_period) => {
              const reset = invoice_reset_period as InvoiceIssueSettings['invoice_reset_period']
              const date = reset === 'yearly' && value.invoice_date_component === 'none' ? 'year' : reset === 'monthly' && !MONTH_COMPONENTS.has(value.invoice_date_component) ? 'year_month' : value.invoice_date_component
              setValue({ ...value, invoice_reset_period: reset, invoice_date_component: date })
            }} />
            <div className="invoice-number-preview"><span>{translate('accounting.numberPreview')}</span><strong>{invoiceNumberPreview(value)}</strong></div>
          </div>
          <p className="field-help">{translate('accounting.numberingHistoryHelp')}</p>
        </fieldset>
      </div>
      <div className="form-actions"><button type="submit" className="primary-button" disabled={busy}>{busy ? translate('accounting.saving') : translate('accounting.saveSettings')}</button></div>
    </form>}
  </>
}

function Field({ label, value, onChange, type = 'text', required = true, autoFocus = false }: { label: string; value: string; onChange: (value: string) => void; type?: string; required?: boolean; autoFocus?: boolean }) {
  return <label><span>{label}</span><input autoFocus={autoFocus} required={required} type={type} min={type === 'number' ? 0 : undefined} value={value} onChange={(event) => onChange(event.target.value)} /></label>
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: ReadonlyArray<readonly [string, string]>; onChange: (value: string) => void }) {
  return <label><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}>{options.map(([optionValue, text]) => <option key={optionValue || 'none'} value={optionValue}>{text}</option>)}</select></label>
}

const DATE_OPTIONS = [
  ['none', 'No date'], ['year', 'Year · 2026'], ['short_year', 'Short year · 26'],
  ['year_month', 'Year + month · 202608'], ['short_year_month', 'Short year + month · 2608'],
  ['month_year', 'Month + year · 082026'], ['month_short_year', 'Month + short year · 0826'],
  ['year_month_code', 'Year + month letter · 2026H'], ['short_year_month_code', 'Short year + month letter · 26H'],
] as const
const SEPARATOR_OPTIONS = [['-', 'Hyphen · -'], ['/', 'Slash · /'], ['.', 'Period · .'], ['', 'None']] as const
const DIGIT_OPTIONS = Array.from({ length: 12 }, (_, index) => [String(index + 1), String(index + 1)] as const)
const RESET_OPTIONS = [['never', 'Never'], ['yearly', 'Each year'], ['monthly', 'Each month']] as const
const MONTH_COMPONENTS = new Set<InvoiceDateComponent>(['year_month', 'short_year_month', 'month_year', 'month_short_year', 'year_month_code', 'short_year_month_code'])

function invoiceNumberPreview(settings: InvoiceIssueSettings): string {
  const dates: Record<InvoiceDateComponent, string> = {
    none: '', year: '2026', short_year: '26', year_month: '202608', short_year_month: '2608',
    month_year: '082026', month_short_year: '0826', year_month_code: '2026H', short_year_month_code: '26H',
  }
  return [settings.invoice_prefix, dates[settings.invoice_date_component], '1'.padStart(settings.invoice_sequence_digits, '0')]
    .filter(Boolean).join(settings.invoice_separator)
}
