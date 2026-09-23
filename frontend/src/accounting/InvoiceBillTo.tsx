import { translate } from '../i18n/localization'
import type { InvoiceDraft } from './api'

export function InvoiceBillTo({ identity }: { identity: NonNullable<InvoiceDraft['bill_to']> }) {
  const locality = [identity.city, [identity.region, identity.postal_code].filter(Boolean).join(' ')].filter(Boolean).join(', ')
  const address = [identity.address_line_1, identity.address_line_2, locality, identity.country_code].filter(Boolean)
  return <dl className="invoice-metadata"><div><dt>{translate('organizations.legalName')}</dt><dd>{identity.legal_name || identity.display_name || '—'}</dd></div><div><dt>{translate('organizations.billingContact')}</dt><dd>{identity.contact_name || '—'}</dd></div><div><dt>{translate('organizations.billingEmail')}</dt><dd>{identity.billing_email || '—'}</dd></div><div><dt>{translate('organizations.billingPhone')}</dt><dd>{identity.phone || '—'}</dd></div><div><dt>{translate('organizations.billingAddress')}</dt><dd>{address.length ? address.map((line) => <span key={line}>{line}<br /></span>) : '—'}</dd></div></dl>
}
