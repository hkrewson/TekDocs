import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { CollectionPagination } from '../CollectionPagination'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { InventoryQuery, NetworkDevice, NetworksClient } from './api'
import { networkText as t } from './networkText'

export function RackDevices({ rackId, workspace, client }: { rackId: string; workspace: WorkspaceContext; client: NetworksClient }) {
  const [params, setParams] = useSearchParams()
  const requested = Number(params.get('racks_devices_page'))
  const page = Number.isSafeInteger(requested) && requested > 0 ? requested : 1
  const size = Number(params.get('racks_devices_size'))
  const pageSize = [25, 50, 100].includes(size) ? size : 25
  const ordering = params.get('racks_devices_order') ?? 'rack_unit'
  const selected = params.get('racks_device')
  const previous = useRef<string | null>(null)
  const queryText = JSON.stringify({ rack_id: rackId, q: params.get('racks_devices_q') ?? '', page, page_size: pageSize, ordering })
  const query = useMemo(() => JSON.parse(queryText) as InventoryQuery, [queryText])
  const key = `${workspace.kind}:${workspace.id}:${queryText}`
  const detailKey = `${workspace.kind}:${workspace.id}:${rackId}:${selected}`
  const [response, setResponse] = useState<{ key: string; value?: Awaited<ReturnType<NetworksClient['deviceCollection']>> } | null>(null)
  const [detail, setDetail] = useState<{ key: string; value?: NetworkDevice } | null>(null)
  const [reload, setReload] = useState(0)
  useEffect(() => { const controller = new AbortController(); client.deviceCollection(workspace, query, controller.signal).then((value) => { if (!controller.signal.aborted) setResponse({ key, value }) }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) }); return () => controller.abort() }, [client, workspace, query, key, reload])
  useEffect(() => { if (!selected) return; const controller = new AbortController(); client.deviceDetail(workspace, selected, controller.signal).then((value) => { if (!controller.signal.aborted) setDetail({ key: detailKey, ...(value.rack_id === rackId ? { value } : {}) }) }).catch(() => { if (!controller.signal.aborted) setDetail({ key: detailKey }) }); return () => controller.abort() }, [workspace, client, selected, detailKey, rackId])
  function browse(values: Record<string, string | null>) { const next = new URLSearchParams(params); if (!('racks_devices_page' in values) && !('racks_device' in values)) next.delete('racks_devices_page'); for (const [name, value] of Object.entries(values)) { if (value) next.set(name, value); else next.delete(name) } setParams(next) }
  const result = response?.key === key ? response : null
  const record = detail?.key === detailKey ? detail : null
  useEffect(() => {
    if (selected) previous.current = selected
    else if (result?.value && previous.current) { document.getElementById(`rack-device-${previous.current}`)?.focus(); previous.current = null }
  }, [selected, result])
  if (selected) return <section aria-label={t('rackDevices')}>
    <button type="button" className="secondary-button" onClick={() => browse({ racks_device: null })}>{t('rackDeviceBack')}</button>
    {!record ? <p role="status">{translate('collections.loading')}</p> : !record.value ? <p role="alert">{t('rackDeviceUnavailable')}</p> : <>
      <h3 tabIndex={-1} ref={(element) => element?.focus()}>{record.value.name}</h3>
      <dl className="record-facts">{[
        [t('rackDeviceRole'), record.value.role], [translate('collections.status'), record.value.status], [t('rackDeviceUnit'), record.value.rack_unit], [t('rackDeviceUnits'), record.value.rack_units], [t('site'), record.value.site_name], [t('location'), record.value.location_name], [t('rackDeviceAsset'), record.value.hardware_asset_name || t('rackDeviceAssetUnavailable')],
      ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? translate('collections.missing')}</dd></div>)}</dl>
    </>}
  </section>
  return <section aria-label={t('rackDevices')}>
    <form className="collection-search" key={query.q} onSubmit={(event) => { event.preventDefault(); const value = new FormData(event.currentTarget).get('q'); browse({ racks_devices_q: typeof value === 'string' ? value : '' }) }}><input type="search" name="q" maxLength={240} defaultValue={query.q} aria-label={t('rackDevicesSearch')} /><button className="secondary-button" type="submit">{translate('collections.searchAction')}</button></form>
    <div className="collection-toolbar"><label>{translate('collections.pageSize')}<select value={pageSize} onChange={(event) => browse({ racks_devices_size: event.target.value })}>{[25, 50, 100].map((value) => <option key={value}>{value}</option>)}</select></label><label>{t('rackDeviceOrder')}<select value={ordering} onChange={(event) => browse({ racks_devices_order: event.target.value })}>{[['rack_unit', t('rackDeviceUnit')], ['name', t('name')], ['role', t('rackDeviceRole')], ['status', translate('collections.status')]].flatMap(([id, label]) => [<option key={id} value={id}>{label} ↑</option>, <option key={`-${id}`} value={`-${id}`}>{label} ↓</option>])}</select></label></div>
    {!result ? <p role="status">{translate('collections.loading')}</p> : !result.value ? <p role="alert">{t('rackDevicesFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
      {result.value.results.length ? <dl className="record-facts">{result.value.results.map((row) => <div key={row.id}><dt><button className="collection-name" id={`rack-device-${row.id}`} type="button" onClick={() => browse({ racks_device: row.id })}>{row.name}</button></dt><dd>{translate('collections.status')}: {row.status}</dd><dd>{t('rackDeviceUnit')}: {row.rack_unit} · {t('rackDeviceUnits')}: {row.rack_units}</dd></div>)}</dl> : <p>{t('rackDevicesEmpty')}</p>}
      <CollectionPagination label={t('rackDevices')} page={page} pageSize={pageSize} count={result.value.count} hasMore={result.value.has_more} onPageChange={(value) => browse({ racks_devices_page: String(value) })} />
    </>}
  </section>
}
