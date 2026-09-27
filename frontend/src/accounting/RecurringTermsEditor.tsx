import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { formatPlainDate, translate as t } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { RecurringClient, RecurringSchedule, RecurringTerms, RecurringTermsPreview } from './recurringApi'
import type { TaxRateChoice } from './api'

type Draft = { effective_from: string; description: string; quantity: string; unit_amount: string; due_days: string; tax: string }
const draftFor = (terms: RecurringTerms): Draft => ({
  effective_from: '', description: terms.description, quantity: terms.quantity,
  unit_amount: terms.unit_amount, due_days: String(terms.due_days), tax: terms.tax_rate_id ?? '__none__',
})

export function RecurringTermsEditor({ workspace, schedule, businessDate, client, saved, cancel }: {
  workspace: WorkspaceContext
  schedule: RecurringSchedule
  businessDate: string
  client: RecurringClient
  saved: (terms: RecurringTerms) => void
  cancel: () => void
}) {
  const latest = useMemo(() => [...schedule.terms].sort((a, b) => b.version - a.version)[0], [schedule.terms])
  const initial = useMemo(() => draftFor(latest), [latest])
  const [draft, setDraft] = useState(initial)
  const [source, setSource] = useState<Awaited<ReturnType<RecurringClient['reviewSource']>> | null>(null)
  const [taxes, setTaxes] = useState<TaxRateChoice[]>([])
  const [preview, setPreview] = useState<RecurringTermsPreview | null>(null)
  const [expiresAt, setExpiresAt] = useState(0)
  const [expired, setExpired] = useState(false)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState(false)
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial)
  const finishCancel = () => { setDraft(initial); cancel() }
  const attempt = useUnsavedChanges(dirty, busy, finishCancel, true)

  async function refreshSource() {
    setBusy(true); setError(false); setPreview(null); setExpired(false)
    try {
      const [review, rates] = await Promise.all([
        client.reviewSource(workspace, schedule.contract_cost_id), client.taxes(workspace),
      ])
      setSource(review); setTaxes(rates)
    } catch { setError(true) }
    finally { setBusy(false) }
  }
  useEffect(() => {
    let active = true
    Promise.all([client.reviewSource(workspace, schedule.contract_cost_id), client.taxes(workspace)])
      .then(([review, rates]) => { if (active) { setSource(review); setTaxes(rates) } })
      .catch(() => { if (active) setError(true) })
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [client, schedule.contract_cost_id, workspace])
  useEffect(() => {
    if (!preview) return
    const timer = window.setTimeout(() => setExpired(true), Math.max(0, expiresAt - Date.now()))
    return () => window.clearTimeout(timer)
  }, [preview, expiresAt])

  function change(field: keyof Draft, value: string) {
    setDraft((current) => ({ ...current, [field]: value })); setPreview(null); setExpired(false); setError(false)
  }
  async function review(event: FormEvent) {
    event.preventDefault()
    if (!source || busy) return
    setBusy(true); setError(false); setPreview(null); setExpired(false)
    const requestedAt = Date.now()
    try {
      const result = await client.previewTerms(workspace, schedule.id, {
        expected_terms_id: latest.id,
        expected_source_digest: source.source_digest,
        effective_from: draft.effective_from,
        description: draft.description,
        quantity: draft.quantity,
        unit_amount: draft.unit_amount,
        currency: latest.currency,
        due_days: Number(draft.due_days),
        tax_rate_id: draft.tax === '__none__' ? null : draft.tax,
      })
      setPreview(result); setExpiresAt(requestedAt + result.expires_in_seconds * 1000)
    } catch { setError(true) }
    finally { setBusy(false) }
  }
  async function apply() {
    if (!preview || busy) return
    if (Date.now() >= expiresAt) { setExpired(true); return }
    setBusy(true); setError(false)
    try { saved(await client.applyTerms(workspace, schedule.id, preview.preview_token)) }
    catch { setError(true) } // Preserve the signed token so an uncertain response can be retried safely.
    finally { setBusy(false) }
  }
  const projection = (label: string, value: RecurringTermsPreview['current']) => <section>
    <h5>{label}</h5>
    <ul className="plain-detail-list">
      <li><span>{t('recurring.termsEffective')}</span><strong>{formatPlainDate(value.effective_from)}</strong></li>
      <li><span>{t('enrollment.description')}</span><strong>{value.description}</strong></li>
      <li><span>{t('recurring.termsPrice')}</span><strong>{value.currency} {value.unit_amount} × {value.quantity}</strong></li>
      <li><span>{t('recurring.termsTotal')}</span><strong>{value.currency} {value.total}</strong></li>
      <li><span>{t('enrollment.due')}</span><strong>{value.due_days}</strong></li>
    </ul>
  </section>

  return <section aria-labelledby="terms-editor-title">
    <h4 id="terms-editor-title">{t('recurring.termsTitle')}</h4>
    <p>{t('recurring.termsHelp')}</p>
    {error && <p role="alert">{t('recurring.termsFailed')}</p>}
    {!source && !error && <p role="status">{t('recurring.termsLoading')}</p>}
    {source && <>
      <p>{t('recurring.termsSource', { label: source.source.label, currency: source.source.currency, amount: source.source.amount, quantity: source.source.quantity })}</p>
      <button type="button" className="secondary-button" disabled={busy} onClick={() => { void refreshSource() }}>{t('enrollment.refresh')}</button>
      <form className="record-form" onSubmit={(event) => { void review(event) }}>
        <label><span>{t('recurring.termsEffective')}</span><input type="date" required min={businessDate} disabled={busy} value={draft.effective_from} onChange={(event) => change('effective_from', event.target.value)} /></label>
        <label><span>{t('enrollment.description')}</span><input required maxLength={1000} disabled={busy} value={draft.description} onChange={(event) => change('description', event.target.value)} /></label>
        <label><span>{t('enrollment.currency')}</span><input readOnly value={latest.currency} /></label>
        <label><span>{t('enrollment.price')}</span><input required inputMode="decimal" disabled={busy} value={draft.unit_amount} onChange={(event) => change('unit_amount', event.target.value)} /></label>
        <label><span>{t('enrollment.quantity')}</span><input required inputMode="decimal" disabled={busy} value={draft.quantity} onChange={(event) => change('quantity', event.target.value)} /></label>
        <label><span>{t('enrollment.due')}</span><input type="number" min={0} max={3650} step={1} required disabled={busy} value={draft.due_days} onChange={(event) => change('due_days', event.target.value)} /></label>
        <label><span>{t('enrollment.tax')}</span><select required disabled={busy} value={draft.tax} onChange={(event) => change('tax', event.target.value)}><option value="__none__">{t('enrollment.noTax')}</option>{taxes.map((rate) => <option key={rate.id} value={rate.id}>{t(rate.inclusive ? 'enrollment.taxInclusive' : 'enrollment.taxExclusive', { name: rate.name, rate: rate.rate })}</option>)}</select></label>
        <p>{t('recurring.termsBoundaryHelp')}</p>
        <div className="form-actions"><button type="submit" className="primary-button" disabled={busy}>{t('recurring.termsReview')}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => attempt(finishCancel)}>{t('common.cancel')}</button></div>
      </form>
    </>}
    {error && !source && <button type="button" className="secondary-button" disabled={busy} onClick={() => { void refreshSource() }}>{t('recurring.retry')}</button>}
    {preview && <section aria-labelledby="terms-review-title">
      <h4 id="terms-review-title">{t('recurring.termsReviewTitle')}</h4>
      {preview.source_changed && <p role="status">{t('recurring.termsSourceChanged')}</p>}
      <div className="record-form-grid">{projection(t('recurring.termsCurrent'), preview.current)}{projection(t('recurring.termsProposed'), preview.proposed)}</div>
      <p>{t('recurring.termsReviewHelp')}</p>
      {expired && <p role="status">{t('recurring.termsExpired')}</p>}
      <button type="button" className="primary-button" disabled={busy || expired} onClick={() => { void apply() }}>{t('recurring.termsApply')}</button>
    </section>}
  </section>
}
