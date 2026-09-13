import { useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router'
import { translate } from '../i18n/localization'
import { CollectionTable } from '../collections/CollectionTable'
import { CollectionPagination } from '../CollectionPagination'
import { ColumnChooser } from '../collections/ColumnChooser'
import { browserCollectionPreferences, defaultPreferences } from '../collections/preferences'
import type { CollectionPreferences } from '../collections/preferences'
import { FilterMenu } from '../FilterMenu'
import { NavigationGuardContext, useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { AddressQuery, AddressSummary, NetworkIPAddress, NetworksClient } from './api'
import { networkText as t } from './networkText'

const columns = ['name', 'status', 'dns_name'] as const
const labels = { name: t('address'), status: t('addressStatus'), dns_name: t('dnsName') }
const statuses = ['active', 'reserved', 'dhcp', 'deprecated'] as const

export function NetworkAddresses({ workspace, subnetId, client, preferenceClient = browserCollectionPreferences }: { workspace: WorkspaceContext; subnetId: string; client: NetworksClient; preferenceClient?: typeof browserCollectionPreferences }) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const [preferences, setPreferences] = useState<CollectionPreferences | null>(null)
  const [response, setResponse] = useState<{ key: string; result?: Awaited<ReturnType<NetworksClient['addressCollection']>> } | null>(null)
  const [detail, setDetail] = useState<{ key: string; record?: NetworkIPAddress } | null>(null)
  const [reload, setReload] = useState(0)
  const [notice, setNotice] = useState('')
  const [pending, setPending] = useState<URLSearchParams | null>(null)
  const guarded = useContext(NavigationGuardContext)!.isGuarded
  const changed = useRef<string | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const previousAddress = useRef<string | null>(null)
  const selected = params.get('address')
  const requested = Number(params.get('address_page') ?? 1)
  const page = Number.isSafeInteger(requested) && requested > 0 ? requested : 1
  const size = Number(params.get('address_size'))
  const pageSize = [25, 50, 100].includes(size) ? size : preferences?.page_size ?? 25
  const queryText = JSON.stringify({ subnet_id: subnetId, q: params.get('address_q') ?? '', page, page_size: pageSize, ordering: params.get('address_order') ?? 'name', ...(params.get('address_status') ? { status: params.get('address_status') } : {}) })
  const query = useMemo(() => JSON.parse(queryText) as AddressQuery, [queryText])
  const key = `${workspace.kind}:${workspace.id}:${queryText}`
  const detailKey = `${workspace.kind}:${workspace.id}:${subnetId}:${selected}`
  const result = response?.key === key ? response.result : null
  const record = detail?.key === detailKey ? detail.record : null
  useEffect(() => { const controller = new AbortController(); preferenceClient.load(workspace, 'network-addresses', columns, controller.signal).then((value) => { if (!controller.signal.aborted) setPreferences(value) }).catch(() => { if (!controller.signal.aborted) setPreferences(defaultPreferences(columns)) }); return () => controller.abort() }, [workspace, preferenceClient])
  useEffect(() => { if (!preferences) return; const controller = new AbortController(); client.addressCollection(workspace, query, controller.signal).then((value) => { if (controller.signal.aborted) return; setResponse({ key, result: value }); if (changed.current) { setNotice(translate(value.results.some((row) => row.id === changed.current) ? 'collections.updated' : 'collections.updatedOutside')); changed.current = null } }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) }); return () => controller.abort() }, [workspace, client, key, query, preferences, reload])
  useEffect(() => { if (!selected || selected === 'new') return; const controller = new AbortController(); client.addressDetail(workspace, selected, controller.signal).then((value) => { if (!controller.signal.aborted) setDetail({ key: detailKey, ...(value.subnet_id === subnetId ? { record: value } : {}) }) }).catch(() => { if (!controller.signal.aborted) setDetail({ key: detailKey }) }); return () => controller.abort() }, [workspace, client, selected, detailKey, subnetId])
  useEffect(() => { if (!pending || guarded) return; const frame = requestAnimationFrame(() => { setParams(pending, { replace: true, state: location.state as unknown }); setPending(null) }); return () => cancelAnimationFrame(frame) }, [pending, guarded, setParams, location.state])
  useEffect(() => { if (selected) previousAddress.current = selected; else if (result && previousAddress.current) { (document.getElementById(`ip-${previousAddress.current}`) ?? heading.current)?.focus(); previousAddress.current = null } }, [selected, result])
  function next(values: Record<string, string | null>) { const changedParams = new URLSearchParams(params); for (const [name, value] of Object.entries(values)) { if (value) changedParams.set(name, value); else changedParams.delete(name) } return changedParams }
  function browse(values: Record<string, string | null>) { setParams(next({ ...(!('address_page' in values) && !('address' in values) ? { address_page: null } : {}), ...values }), { state: location.state as unknown }) }
  function saved(value: NetworkIPAddress) { changed.current = value.id; setDetail({ key: `${workspace.kind}:${workspace.id}:${subnetId}:${value.id}`, record: value }); setPending(next({ address: value.id })); setReload(reload + 1) }
  return <section aria-label={t('addresses')}>
    {notice && <p role="status">{notice}</p>}
    {selected ? <>
      {selected === 'new' || record ? <AddressRecord key={selected} record={record ?? null} subnetId={subnetId} workspace={workspace} client={client} canManage={Boolean(result?.can_manage)} onSaved={saved} onReturn={() => browse({ address: null })} /> : <><button type="button" className="secondary-button" onClick={() => browse({ address: null })}>{t('backAddresses')}</button><p role={detail?.key === detailKey ? 'alert' : 'status'}>{translate(detail?.key === detailKey ? 'collections.recordUnavailable' : 'collections.loading')}</p></>}
    </> : <>
      <h2 ref={heading} tabIndex={-1}>{t('addresses')}</h2>
      {result?.can_manage && <button type="button" className="primary-button" onClick={() => browse({ address: 'new' })}>{t('newAddress')}</button>}
      <div className="collection-toolbar">
        <form key={query.q} className="address-search collection-search" onSubmit={(event) => { event.preventDefault(); const value = new FormData(event.currentTarget).get('q'); browse({ address_q: typeof value === 'string' ? value : '' }) }}><input type="search" name="q" defaultValue={query.q} aria-label={t('searchAddresses')} /><button type="submit" className="secondary-button">{t('searchAction')}</button></form>
        <FilterMenu groups={[{ kind: 'choices', label: t('addressStatus'), value: query.status ?? '', choices: [{ value: '', label: translate('collections.all') }, ...statuses.map((value) => ({ value, label: t(value) }))], onChange: (value) => browse({ address_status: value || null }) }]} activeCount={Number(Boolean(query.status))} onClear={() => browse({ address_status: null })} />
        {preferences && <ColumnChooser preferences={preferences} labels={labels} onSave={async (selectedColumns) => setPreferences(await preferenceClient.save(workspace, 'network-addresses', { columns: selectedColumns, page_size: pageSize as 25 | 50 | 100 }))} onReset={async () => { setPreferences(await preferenceClient.reset(workspace, 'network-addresses')); setPending(next({ address_size: null, address_page: null })) }} />}
        <label>{translate('collections.pageSize')}<select value={pageSize} onChange={(event) => { const value = Number(event.target.value) as 25 | 50 | 100; browse({ address_size: String(value) }); void preferenceClient.save(workspace, 'network-addresses', { columns: preferences?.columns ?? [...columns], page_size: value }).then(setPreferences).catch(() => setNotice(translate('collections.preferenceFailed'))) }}>{[25, 50, 100].map((value) => <option key={value}>{value}</option>)}</select></label>
      </div>
      {query.status && <button className="row-action" type="button" onClick={() => browse({ address_status: null })}>{t('addressStatus')}: {statuses.includes(query.status as typeof statuses[number]) ? t(query.status as typeof statuses[number]) : query.status} ×</button>}
      <label className="collection-mobile-order">{t('addressOrder')}<select value={query.ordering} onChange={(event) => browse({ address_order: event.target.value })}>{columns.flatMap((column) => [<option key={column} value={column}>{labels[column]} ↑</option>, <option key={`-${column}`} value={`-${column}`}>{labels[column]} ↓</option>])}</select></label>
      {!response || response.key !== key ? <p role="status">{translate('collections.loading')}</p> : !result ? <p role="alert">{t('addressesFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
        <p>{t('addressCount', { count: result.count })}</p>
        {result.results.length ? <CollectionTable<AddressSummary & { name: string }> label={t('addresses')} rows={result.results.map((row) => ({ ...row, name: row.address }))} columns={(preferences?.columns ?? columns).map((column) => ({ id: column, label: labels[column as keyof typeof labels], render: (row) => column === 'name' ? <button className="collection-name" id={`ip-${row.id}`} type="button" onClick={() => browse({ address: row.id })}>{row.address}</button> : column === 'status' ? t(row.status) : row.dns_name || translate('collections.missing') }))} ordering={query.ordering} onOrder={(value) => browse({ address_order: value })} selectable={false} selected={new Set()} onSelection={() => {}} /> : <p>{t('addressesEmpty')}</p>}
        <CollectionPagination label={t('addresses')} page={page} pageSize={pageSize} count={result.count} hasMore={result.has_more} onPageChange={(value) => browse({ address_page: String(value) })} />
      </>}
    </>}
  </section>
}

type AddressForm = Pick<NetworkIPAddress, 'address' | 'status' | 'dns_name' | 'description'>
function AddressRecord({ record, subnetId, workspace, client, canManage, onSaved, onReturn }: { record: NetworkIPAddress | null; subnetId: string; workspace: WorkspaceContext; client: NetworksClient; canManage: boolean; onSaved: (record: NetworkIPAddress) => void; onReturn: () => void }) {
  const initial: AddressForm = record ? { address: record.address, status: record.status, dns_name: record.dns_name, description: record.description } : { address: '', status: 'active', dns_name: '', description: '' }
  const [form, setForm] = useState(initial)
  const [editing, setEditing] = useState(!record)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  const attempt = useUnsavedChanges(editing && JSON.stringify(form) !== JSON.stringify(initial), busy, () => { setEditing(false); setForm(initial) }, editing)
  useEffect(() => { heading.current?.focus() }, [record?.id])
  async function save() { setBusy(true); setError(''); try { const value = record ? await client.updateIPAddress(workspace, record.id, form) : await client.createIPAddress(workspace, { ...form, subnet_id: subnetId, hardware_asset_id: null }); setEditing(false); onSaved(value) } catch (caught) { setError(caught instanceof Error ? caught.message : t('addressSaveFailed')) } finally { setBusy(false) } }
  return <>
    <button className="secondary-button" type="button" onClick={onReturn}>{t('backAddresses')}</button>
    <h2 ref={heading} tabIndex={-1}>{record?.address ?? t('newAddress')}</h2>
    {error && <p role="alert">{error}</p>}
    {editing && canManage ? <form className="network-inline-editor" onSubmit={(event) => { event.preventDefault(); void save() }}><fieldset disabled={busy}>
      <label>{t('address')}<input required maxLength={45} value={form.address} onChange={(event) => setForm({ ...form, address: event.target.value })} /></label>
      <label>{t('addressStatus')}<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as AddressForm['status'] })}>{statuses.map((status) => <option key={status} value={status}>{t(status)}</option>)}</select></label>
      <label>{t('dnsName')}<input maxLength={253} value={form.dns_name} onChange={(event) => setForm({ ...form, dns_name: event.target.value })} /></label>
      <label>{t('description')}<textarea rows={4} maxLength={4000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
      <div className="form-actions"><button type="submit" className="primary-button" disabled={busy}>{busy ? translate('common.saving') : t('saveAddress')}</button><button type="button" className="secondary-button" onClick={() => { if (record) attempt(() => setEditing(false)); else onReturn() }}>{translate('common.cancel')}</button></div>
    </fieldset></form> : record ? <>
      <dl className="record-facts">{[[t('addressStatus'), t(record.status)], [t('dnsName'), record.dns_name || translate('collections.missing')], [t('addressAssignment'), record.hardware_asset_name || record.device_name || translate('collections.missing')], [t('addressInterface'), record.interface_name || translate('collections.missing')]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      <p className="network-notes">{record.description || t('noDescription')}</p>
      {canManage && <button className="secondary-button" type="button" onClick={() => { setForm(initial); setEditing(true) }}>{t('editAddress')}</button>}
    </> : <p>{t('addressDenied')}</p>}
  </>
}
