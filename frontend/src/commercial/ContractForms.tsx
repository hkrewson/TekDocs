import type { FormEvent } from 'react'
import { translate } from '../i18n/localization'
import type { CommercialContract, ContractCost } from './api'
import type { ContractForm, CostForm } from './contractValues'
import { contractText as t } from './contractText'

export function ContractEditor({ title, value, setValue, providers, busy, cancel, submit, canSubmit = true }: { title: string; value: ContractForm; setValue: (value: ContractForm) => void; providers: Array<{ id: string; name: string }>; canSubmit?: boolean; busy: boolean; cancel: () => void; submit: () => void }) {
  function save(event: FormEvent) { event.preventDefault(); submit() }
  return <form className="contract-editor" aria-label={title} onSubmit={save}><fieldset disabled={busy}><div className="section-heading"><h2 id="contract-editor-title">{title}</h2></div><p className="workspace-area-note">{translate('contracts.costHelp')}</p><div className="form-grid">
    <Field label={t('contractName')} value={value.name} onChange={(name) => setValue({ ...value, name })} />
    <label><span>{t('provider')}</span><select required value={value.provider_id} onChange={(event) => setValue({ ...value, provider_id: event.target.value })}><option value="">{t('chooseProvider')}</option>{providers.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
    <Choice label={t('kind')} value={value.kind} items={['service', 'support', 'lease', 'subscription', 'other']} onChange={(kind) => setValue({ ...value, kind: kind as CommercialContract['kind'] })} />
    <Choice label={t('status')} value={value.status} items={['draft', 'active', 'expired', 'terminated']} onChange={(status) => setValue({ ...value, status: status as CommercialContract['status'] })} />
    <Field label={t('startsOn')} type="date" value={value.starts_on} onChange={(starts_on) => setValue({ ...value, starts_on })} /><Field label={t('endsOn')} type="date" value={value.ends_on} onChange={(ends_on) => setValue({ ...value, ends_on })} />
    <Field label={t('renewsOn')} type="date" value={value.renews_on} onChange={(renews_on) => setValue({ ...value, renews_on })} /><Field label={t('renewalNoticeDays')} type="number" value={String(value.renewal_notice_days)} onChange={(renewal_notice_days) => setValue({ ...value, renewal_notice_days: Number(renewal_notice_days) })} />
    <Field label={t('reference')} value={value.reference} onChange={(reference) => setValue({ ...value, reference })} /><Field label={t('description')} value={value.description} onChange={(description) => setValue({ ...value, description })} />
    <label className="checkbox-field"><input type="checkbox" checked={value.auto_renew} onChange={(event) => setValue({ ...value, auto_renew: event.target.checked })} /><span>{t('autoRenew')}</span></label>
  </div><Actions busy={busy} disabled={!canSubmit || !value.name.trim() || !value.provider_id} cancel={cancel} label={t('saveContract')} /></fieldset></form>
}

export function CostEditor({ title, submitLabel, value, setValue, busy, cancel, submit }: { title: string; submitLabel: string; value: CostForm; setValue: (value: CostForm) => void; busy: boolean; cancel: () => void; submit: () => void }) {
  function save(event: FormEvent) { event.preventDefault(); submit() }
  return <form className="contract-editor" aria-label={title} onSubmit={save}><fieldset disabled={busy}><div className="section-heading"><h2 id="cost-editor-title">{title}</h2></div><div className="form-grid">
    <Field label={t('costLabel')} value={value.label} onChange={(label) => setValue({ ...value, label })} /><Field label={t('amount')} type="number" step="0.01" value={value.amount} onChange={(amount) => setValue({ ...value, amount })} />
    <Field label={t('currency')} value={value.currency} onChange={(currency) => setValue({ ...value, currency })} /><Choice label={t('billingInterval')} value={value.billing_interval} items={['one_time', 'monthly', 'quarterly', 'annual']} onChange={(billing_interval) => setValue({ ...value, billing_interval: billing_interval as ContractCost['billing_interval'] })} />
    <Field label={t('quantity')} type="number" step="0.001" value={value.quantity} onChange={(quantity) => setValue({ ...value, quantity })} /><Field label={t('reference')} value={value.reference} onChange={(reference) => setValue({ ...value, reference })} />
    <Field label={t('startsOn')} type="date" value={value.starts_on} onChange={(starts_on) => setValue({ ...value, starts_on })} /><Field label={t('endsOn')} type="date" value={value.ends_on} onChange={(ends_on) => setValue({ ...value, ends_on })} />
  </div><Actions busy={busy} disabled={!value.label.trim() || !value.amount || !value.currency} cancel={cancel} label={submitLabel} /></fieldset></form>
}

function Field({ label, value, onChange, type = 'text', step }: { label: string; value: string; onChange: (value: string) => void; type?: string; step?: string }) { return <label><span>{label}</span><input autoFocus={label === t('contractName') || label === t('costLabel')} required={label === t('contractName') || label === t('costLabel')} type={type} step={step} min={type === 'number' ? 0 : undefined} value={value} onChange={(event) => onChange(event.target.value)} /></label> }
function Choice({ label, value, items, onChange }: { label: string; value: string; items: string[]; onChange: (value: string) => void }) { return <label><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}>{items.map((item) => <option value={item} key={item}>{item.replace('_', ' ')}</option>)}</select></label> }
function Actions({ busy, cancel, label, disabled = false }: { disabled?: boolean; busy: boolean; cancel: () => void; label: string }) { return <div className="form-actions"><button type="submit" className="primary-button" disabled={busy || disabled}>{busy ? translate('common.saving') : label}</button><button type="button" className="secondary-button" onClick={cancel}>{translate('common.cancel')}</button></div> }
