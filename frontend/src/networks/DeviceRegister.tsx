import { useLocation, useSearchParams } from 'react-router'
import { browserCollectionPreferences } from '../collections/preferences'
import { translate } from '../i18n/localization'
import { RecordActivity } from '../records/RecordActivity'
import { RecordHeader, RecordSections } from '../records/RecordNavigation'
import type { WorkspaceContext } from '../workspaces/api'
import type { RelationshipsClient } from '../relationships/api'
import { NetworkChildCollection } from './NetworkChildCollection'
import type { ChildCollectionConfig, ChildRecordProps } from './NetworkChildCollection'
import type { NetworkDevice, NetworksClient } from './api'
import { networkText as t } from './networkText'

const columns = ['name', 'netbox_id', 'rack', 'rack_unit', 'rack_units', 'serial_number', 'model_name'] as const
const labels = {
  name: t('name'), netbox_id: t('deviceNetBoxId'), rack: t('deviceRack'), rack_unit: t('rackDeviceUnit'),
  rack_units: t('deviceHeight'), serial_number: t('deviceSerial'), model_name: t('deviceModel'),
}
const config: ChildCollectionConfig<NetworkDevice, NetworkDevice> = {
  key: 'devices', feature: 'network-devices', allowCreate: false, columns, labels, title: t('devices'), back: t('devicesBack'),
  create: t('devicesNew'), search: t('devicesSearch'), order: t('devicesOrder'), failed: t('devicesFailed'),
  empty: t('devicesEmpty'), count: (count) => t('devicesCount', { count }), statuses: [], identity: (row) => row.name,
  value: (row, column) => column === 'netbox_id' ? row.netbox_id ?? translate('collections.missing')
    : column === 'rack' ? row.rack_name || translate('collections.missing')
      : column === 'rack_unit' ? row.rack_unit ?? translate('collections.missing')
        : column === 'rack_units' ? row.rack_units
          : column === 'serial_number' ? row.serial_number || translate('collections.missing')
            : row.model_name || translate('collections.missing'),
  load: (client, workspace, query, signal) => client.deviceCollection(workspace, query, signal),
  read: (client, workspace, id, signal) => client.deviceDetail(workspace, id, signal),
}

export function DeviceRegister({ workspace, client, preferenceClient = browserCollectionPreferences }: {
  workspace: WorkspaceContext; client: NetworksClient; relationshipsClient?: RelationshipsClient;
  preferenceClient?: typeof browserCollectionPreferences
}) {
  return <div className="device-register"><NetworkChildCollection standalone workspace={workspace} subnetId="" client={client} preferenceClient={preferenceClient} config={config} RecordComponent={DeviceRecord} /></div>
}

type Props = ChildRecordProps<NetworkDevice> & { workspace: WorkspaceContext; client: NetworksClient }
function DeviceRecord({ record, workspace }: Props) {
  const [params] = useSearchParams()
  const location = useLocation()
  const section = record && params.get('devices_section') === 'history' ? 'history' : 'overview'
  function href(id: string) { const next = new URLSearchParams(params); next.set('devices_section', id); return `${location.pathname}?${next}` }
  if (!record) return <p role="alert">{translate('collections.recordUnavailable')}</p>
  return <article className="record-page">
    {params.get('devices_full') === 'true' && <RecordHeader title={record.name} recordId={record.id} section={section} />}
    <RecordSections current={section} sections={[
      { id: 'overview', label: translate('collections.overview'), href: href('overview') },
      { id: 'history', label: translate('collections.history'), href: href('history') },
    ]} />
    {section === 'history' ? <RecordActivity workspace={workspace} entityId={record.id} description={t('devicesHistoryHelp')} emptyLabel={t('devicesHistoryEmpty')} deniedLabel={t('devicesHistoryDenied')} /> : <>
      <dl className="record-facts">
        {[
          [t('deviceNetBoxId'), record.netbox_id], [t('deviceRack'), record.rack_name],
          [t('rackDeviceUnit'), record.rack_unit], [t('deviceHeight'), record.rack_units],
          [t('deviceSerial'), record.serial_number], [t('deviceManufacturer'), record.manufacturer_name],
          [t('deviceProduct'), record.product_name], [t('deviceModel'), record.model_name],
          [t('deviceSourceObserved'), record.source_observed_at ? new Date(record.source_observed_at).toLocaleString() : null],
        ].map(([label, value]) => <div key={String(label)}><dt>{label}</dt><dd>{value ?? translate('collections.missing')}</dd></div>)}
      </dl>
    </>}
  </article>
}
