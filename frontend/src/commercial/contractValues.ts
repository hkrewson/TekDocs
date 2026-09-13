import type { CommercialContract, ContractCost } from './api'

export type ContractForm = {
  name: string; provider_id: string; kind: CommercialContract['kind']; status: CommercialContract['status']
  description: string; reference: string; starts_on: string; ends_on: string; renews_on: string
  auto_renew: boolean; renewal_notice_days: number
}
export type CostForm = {
  label: string; amount: string; currency: string; billing_interval: ContractCost['billing_interval']
  quantity: string; starts_on: string; ends_on: string; reference: string
}

export const blankContract: ContractForm = { name: '', provider_id: '', kind: 'service', status: 'draft', description: '', reference: '', starts_on: '', ends_on: '', renews_on: '', auto_renew: false, renewal_notice_days: 0 }
export const blankCost: CostForm = { label: '', amount: '', currency: 'USD', billing_interval: 'monthly', quantity: '1', starts_on: '', ends_on: '', reference: '' }

export function contractForm(record: CommercialContract): ContractForm {
  return Object.fromEntries(Object.keys(blankContract).map((key) => [key, record[key as keyof ContractForm] ?? ''])) as ContractForm
}

export function costForm(record: ContractCost): CostForm {
  return Object.fromEntries(Object.keys(blankCost).map((key) => [key, record[key as keyof CostForm] ?? ''])) as CostForm
}

export function dates<T extends { starts_on: string; ends_on: string }>(values: T) {
  return { ...values, starts_on: values.starts_on || null, ends_on: values.ends_on || null }
}

