import { useEffect, useState } from 'react'
import { RecurringEnrollment } from './RecurringEnrollment'
import { browserEnrollmentClient } from './enrollmentApi'
import type { FormEvent } from 'react'
import { formatPlainDate, translate as t } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { RecurringClient, RecurringPage, RecurringSchedule, RecurringDue, RecurringPreview, RecurringClaim } from './recurringApi'

export function RecurringInvoices({ workspace, client, openInvoice }: {
  workspace: WorkspaceContext; client: RecurringClient; openInvoice: (id: string) => Promise<void>
}) {
  const [enrolling, setEnrolling] = useState(false)
  const [page, setPage] = useState(1)
  const [listing, setListing] = useState<RecurringPage | null>(null)
  const [schedule, setSchedule] = useState<RecurringSchedule | null>(null)
  const [from, setFrom] = useState('')
  const [asOf, setAsOf] = useState('')
  const [due, setDue] = useState<RecurringDue | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [preview, setPreview] = useState<RecurringPreview | null>(null)
  const [claims, setClaims] = useState<readonly RecurringClaim[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const [expiresAt, setExpiresAt] = useState(0)
  const [expired, setExpired] = useState(false)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    client.list(workspace, page, controller.signal).then((result) => {
      if (!controller.signal.aborted) { setListing(result); setAsOf(result.business_date) }
    }).catch(() => { if (!controller.signal.aborted) setError(true) })
    return () => controller.abort()
  }, [workspace, client, page, reload])

  useEffect(() => {
    if (!preview) return
    const timer = window.setTimeout(() => setExpired(true), Math.max(0, expiresAt - Date.now()))
    return () => window.clearTimeout(timer)
  }, [preview, expiresAt])

  function invalidate() { setPreview(null); setClaims([]); setExpired(false); setError(false) }
  function choose(record: RecurringSchedule) {
    invalidate(); setSchedule(record); setDue(null); setSelected([]); setFrom(record.anchor)
  }
  async function loadDue(event: FormEvent) {
    event.preventDefault()
    if (!schedule) return
    invalidate(); setDue(null); setSelected([]); setBusy(true)
    try { setDue(await client.due(workspace, schedule.id, from, asOf)) }
    catch { setError(true) }
    finally { setBusy(false) }
  }
  async function review() {
    if (!schedule) return
    setBusy(true); invalidate()
    const requestedAt = Date.now()
    try {
      const result = await client.preview(workspace, schedule.id, selected, asOf)
      setExpiresAt(requestedAt + result.expires_in_seconds * 1000); setPreview(result)
    } catch { setError(true) }
    finally { setBusy(false) }
  }
  async function apply() {
    if (!schedule || !preview) return
    if (Date.now() >= expiresAt) { setExpired(true); return }
    setBusy(true); setError(false)
    try { setClaims(await client.apply(workspace, schedule.id, preview.preview_token)) }
    catch { setError(true) } // Keep the same token for an uncertain transport result; server claims make retry safe.
    finally { setBusy(false) }
  }
  async function open(id: string) {
    setBusy(true); setError(false)
    try { await openInvoice(id) } catch { setError(true) } finally { setBusy(false) }
  }
  const reasons = {
    disabled: 'recurring.disabled', source_changed: 'recurring.sourceChanged', source_unavailable: 'recurring.sourceUnavailable',
    partial: 'recurring.partial', tax: 'recurring.tax',
  } as const

  return <section className="content-section" aria-labelledby="recurring-title">
    <h2 id="recurring-title">{t('recurring.title')}</h2>
    <p>{t('recurring.help')}</p>
    {!enrolling && <button type="button" className="secondary-button" disabled={busy} onClick={() => setEnrolling(true)}>{t('enrollment.title')}</button>}
    {enrolling && <RecurringEnrollment key={workspace.id} workspace={workspace} client={browserEnrollmentClient} cancel={() => { setEnrolling(false); setPage(1); setReload((value) => value + 1) }} enrolled={(record) => {
      setEnrolling(false); choose(record); setPage(1); setReload((value) => value + 1)
    }} />}
    {error && <p role="alert">{t('recurring.failed')}</p>}
    {!listing && !error && <p role="status">{t('recurring.loading')}</p>}
    {!listing && error && <button type="button" className="secondary-button" onClick={() => { setError(false); setReload((value) => value + 1) }}>{t('recurring.retry')}</button>}
    {!enrolling && listing && <>
      {listing.results.length === 0 && <p>{t('recurring.empty')}</p>}
      <ul className="inventory-list">{listing.results.map((record) => <li key={record.id}>
        <button type="button" disabled={busy} aria-pressed={schedule?.id === record.id} onClick={() => choose(record)}>
          <strong>{record.terms[0]?.description || record.source_label}</strong><span>{record.contract_name} · {record.source_label}</span>
        </button>
      </li>)}</ul>
      <div className="form-actions">
        <button type="button" className="secondary-button" disabled={busy || page === 1} onClick={() => { invalidate(); setSchedule(null); setListing(null); setPage(page - 1) }}>{t('recurring.previous')}</button>
        <button type="button" className="secondary-button" disabled={busy || !listing.has_more} onClick={() => { invalidate(); setSchedule(null); setListing(null); setPage(page + 1) }}>{t('recurring.next')}</button>
      </div>
    </>}
    {!enrolling && schedule && <>
      <h3>{schedule.terms[0]?.description}</h3>
      <p>{t('recurring.approved', { currency: schedule.terms[0]?.currency ?? '', amount: schedule.terms[0]?.unit_amount ?? '', quantity: schedule.terms[0]?.quantity ?? '' })}</p>
      <form className="record-form" onSubmit={(event) => { void loadDue(event) }}>
        <label><span>{t('recurring.from')}</span><input type="date" required disabled={busy} value={from} onChange={(event) => { invalidate(); setDue(null); setSelected([]); setFrom(event.target.value) }} /></label>
        <label><span>{t('recurring.asOf')}</span><input type="date" required disabled={busy} max={listing?.business_date} value={asOf} onChange={(event) => { invalidate(); setDue(null); setSelected([]); setAsOf(event.target.value) }} /></label>
        <p>{t('recurring.windowHelp')}</p>
        <button type="submit" className="secondary-button" disabled={busy}>{t('recurring.find')}</button>
      </form>
      {due && <fieldset disabled={busy}><legend>{t('recurring.periods')}</legend>
        {due.periods.length === 0 && <p>{t('recurring.noPeriods')}</p>}
        {due.periods.map((period) => <div key={period.starts_on}>
          <label><input type="checkbox" disabled={!period.can_generate || claims.length > 0} checked={selected.includes(period.starts_on)} onChange={(event) => { invalidate(); setSelected((current) => event.target.checked ? [...current, period.starts_on] : current.filter((start) => start !== period.starts_on)) }} />{formatPlainDate(period.starts_on)}</label>
          {period.invoice_entity_id ? <button type="button" className="secondary-button" onClick={() => { void open(period.invoice_entity_id!) }}>{t('recurring.openExisting')}</button> : period.blocked_reason && <p>{t(reasons[period.blocked_reason])}</p>}
        </div>)}
        <button type="button" className="secondary-button" disabled={!selected.length || claims.length > 0} onClick={() => { void review() }}>{t('recurring.review')}</button>
      </fieldset>}
      {preview && <section aria-labelledby="recurring-review"><h3 id="recurring-review">{t('recurring.reviewTitle')}</h3>
        <p>{t('recurring.reviewHelp')}</p>
        <ul>{preview.periods.map((period) => <li key={period.starts_on}>{t('recurring.reviewLine', { start: formatPlainDate(period.starts_on), end: formatPlainDate(period.ends_before), due: formatPlainDate(period.due_date), currency: preview.currency, total: period.total })}</li>)}</ul>
        {expired && !claims.length && <p role="status">{t('recurring.expired')}</p>}
        {!claims.length && <button type="button" className="primary-button" disabled={busy || expired} onClick={() => { void apply() }}>{t('recurring.create')}</button>}
      </section>}
      {claims.length > 0 && <div role="status"><p>{t('recurring.created')}</p>{claims.map((claim) => <button type="button" className="secondary-button" key={claim.id} disabled={busy} onClick={() => { void open(claim.invoice_entity_id) }}>{t('recurring.openDated', { date: formatPlainDate(claim.starts_on) })}</button>)}</div>}
    </>}
  </section>
}
