import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { translate as t, formatPlainDate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { RecurringSchedule } from './recurringApi'
import type { EnrollmentClient, EnrollmentReview, EnrollmentSources } from './enrollmentApi'
import type { TaxRateChoice } from './api'

type Terms = { description: string; quantity: string; unit_amount: string; anchor: string; ends_on: string; due_days: string; tax: string }
const empty = (): Terms => ({ description: '', quantity: '', unit_amount: '', anchor: '', ends_on: '', due_days: '', tax: '' })
export function RecurringEnrollment({ workspace, client, enrolled, cancel }: {
  workspace: WorkspaceContext; client: EnrollmentClient; enrolled: (schedule: RecurringSchedule) => void; cancel: () => void
}) {
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [sources, setSources] = useState<EnrollmentSources | null>(null)
  const [review, setReview] = useState<EnrollmentReview | null>(null)
  const [taxes, setTaxes] = useState<TaxRateChoice[]>([])
  const [terms, setTerms] = useState<Terms>(empty)
  const [approved, setApproved] = useState(false)
  const [mustRefresh, setMustRefresh] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    client.sources(workspace, query, page, controller.signal).then((result) => {
      if (!controller.signal.aborted) setSources(result)
    }).catch(() => { if (!controller.signal.aborted) setError(true) })
    return () => controller.abort()
  }, [client, workspace, query, page, retry])

  async function load(id: string, refresh = false) {
    setBusy(true); setApproved(false); setError(false); setMustRefresh(true)
    try {
      const [source, rates] = await Promise.all([client.review(workspace, id), client.taxes(workspace)])
      setReview(source); setTaxes(rates); setMustRefresh(false)
      if (!refresh) setTerms(empty())
    } catch { setError(true) }
    finally { setBusy(false) }
  }
  function change(field: keyof Terms, value: string) { setTerms((current) => ({ ...current, [field]: value })); setApproved(false) }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!review || !approved || mustRefresh || busy) return
    setBusy(true); setError(false)
    try {
      const schedule = await client.enroll(workspace, {
        cost_id: review.source.cost_id, expected_source_digest: review.source_digest,
        description: terms.description, quantity: terms.quantity, unit_amount: terms.unit_amount,
        currency: review.source.currency, anchor: terms.anchor, ends_on: terms.ends_on || null,
        due_days: Number(terms.due_days), tax_rate_id: terms.tax === '__none__' ? null : terms.tax,
      })
      enrolled(schedule)
    } catch { setError(true); setMustRefresh(true); setApproved(false) }
    finally { setBusy(false) }
  }
  const interval = { monthly: 'enrollment.monthly', quarterly: 'enrollment.quarterly', annual: 'enrollment.annual' } as const
  return <section aria-labelledby="enrollment-title">
    <h3 id="enrollment-title">{t('enrollment.title')}</h3>
    <p>{t('enrollment.help')}</p>
    {error && <p role="alert">{t('enrollment.failed')}</p>}
    <label><span>{t('enrollment.search')}</span><input type="search" disabled={busy} value={query} onChange={(event) => { setError(false); setSources(null); setPage(1); setQuery(event.target.value) }} /></label>
    {!sources && !error && <p role="status">{t('enrollment.loading')}</p>}
    {error && !sources && <button type="button" className="secondary-button" onClick={() => { setError(false); setRetry((value) => value + 1) }}>{t('recurring.retry')}</button>}
    {sources && <>
      {!sources.results.length && <p>{t('enrollment.empty')}</p>}
      <ul className="inventory-list">{sources.results.map((source) => <li key={source.id}><button type="button" disabled={busy} aria-pressed={review?.source.cost_id === source.id} onClick={() => { void load(source.id) }}><strong>{source.label}</strong><span>{source.contract_name}</span></button></li>)}</ul>
      <div className="form-actions"><button type="button" className="secondary-button" disabled={busy || page === 1} onClick={() => { setSources(null); setPage(page - 1) }}>{t('enrollment.previous')}</button><button type="button" className="secondary-button" disabled={busy || !sources.has_more} onClick={() => { setSources(null); setPage(page + 1) }}>{t('enrollment.next')}</button></div>
    </>}
    {review && <>
      <h4>{t('enrollment.sourceHeading')}</h4>
      <p>{review.source.label}</p>
      <p>{t('enrollment.sourceValues', { currency: review.source.currency, amount: review.source.amount, quantity: review.source.quantity, interval: t(interval[review.source.interval]) })}</p>
      <p>{review.earliest_anchor ? t('enrollment.startBound', { date: formatPlainDate(review.earliest_anchor) }) : t('enrollment.noStartBound')}</p>
      <p>{review.latest_end ? t('enrollment.endBound', { date: formatPlainDate(review.latest_end) }) : t('enrollment.noEndBound')}</p>
      <button type="button" className="secondary-button" disabled={busy} onClick={() => { void load(review.source.cost_id, true) }}>{t('enrollment.refresh')}</button>
      <form className="record-form" onSubmit={(event) => { void submit(event) }}>
        <h4>{t('enrollment.sellHeading')}</h4>
        <label><span>{t('enrollment.description')}</span><input required maxLength={1000} disabled={busy} value={terms.description} onChange={(event) => change('description', event.target.value)} /></label>
        <label><span>{t('enrollment.currency')}</span><input readOnly value={review.source.currency} /></label>
        <label><span>{t('enrollment.price')}</span><input required inputMode="decimal" disabled={busy} value={terms.unit_amount} onChange={(event) => change('unit_amount', event.target.value)} /></label>
        <label><span>{t('enrollment.quantity')}</span><input required inputMode="decimal" disabled={busy} value={terms.quantity} onChange={(event) => change('quantity', event.target.value)} /></label>
        <label><span>{t('enrollment.anchor')}</span><input type="date" required min={review.earliest_anchor ?? undefined} max={review.latest_end ?? undefined} disabled={busy} value={terms.anchor} onChange={(event) => change('anchor', event.target.value)} /></label>
        <label><span>{t('enrollment.end')}</span><input type="date" required={Boolean(review.latest_end)} min={terms.anchor || review.earliest_anchor || undefined} max={review.latest_end ?? undefined} disabled={busy} value={terms.ends_on} onChange={(event) => change('ends_on', event.target.value)} /></label>
        <label><span>{t('enrollment.due')}</span><input type="number" min={0} max={3650} step={1} required disabled={busy} value={terms.due_days} onChange={(event) => change('due_days', event.target.value)} /></label>
        <label><span>{t('enrollment.tax')}</span><select required disabled={busy} value={terms.tax} onChange={(event) => change('tax', event.target.value)}><option value="">{t('enrollment.chooseTax')}</option><option value="__none__">{t('enrollment.noTax')}</option>{taxes.map((rate) => <option key={rate.id} value={rate.id}>{t(rate.inclusive ? 'enrollment.taxInclusive' : 'enrollment.taxExclusive', { name: rate.name, rate: rate.rate })}</option>)}</select></label>
        <p>{t('enrollment.taxHelp')}</p><p>{t('enrollment.fixedHelp')}</p>
        <label><input type="checkbox" checked={approved} disabled={busy || mustRefresh} onChange={(event) => setApproved(event.target.checked)} />{t('enrollment.approve')}</label>
        <button type="submit" className="primary-button" disabled={busy || !approved || mustRefresh}>{t('enrollment.save')}</button>
      </form>
    </>}
    <button type="button" className="secondary-button" disabled={busy} onClick={cancel}>{t('common.cancel')}</button>
  </section>
}
