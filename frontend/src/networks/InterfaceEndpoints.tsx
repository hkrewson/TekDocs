import { useEffect, useRef, useState } from 'react'
import { translate } from '../i18n/localization'
import { browserCollectionPreferences } from '../collections/preferences'
import { CollectionPagination } from '../CollectionPagination'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { ListResult, NetworkIPAddress, NetworkInterface, NetworkMACAddress, NetworkSubnet, NetworksClient } from './api'
import { NetworkChildCollection } from './NetworkChildCollection'
import type { ChildCollectionConfig, ChildRecordProps } from './NetworkChildCollection'
import { networkText as t } from './networkText'

type Endpoint = NetworkIPAddress | NetworkMACAddress
type Summary = Omit<NetworkIPAddress, 'description'> | Omit<NetworkMACAddress, 'description'>
type Kind = 'ip' | 'mac'
const statuses = ['active', 'reserved', 'dhcp', 'deprecated'] as const
const configs: Record<Kind, ChildCollectionConfig<Summary, Endpoint>> = {
  ip: {
    key: 'interface_ip', feature: 'interface-ip-addresses', parentField: 'interface_id', columns: ['name', 'status', 'dns_name'],
    labels: { name: t('address'), status: t('addressStatus'), dns_name: t('dnsName') },
    title: t('endpointIPs'), back: t('endpointIPBack'), create: t('endpointIPAdd'), search: t('endpointIPSearch'), order: t('endpointIPOrder'), failed: t('endpointIPFailed'), empty: t('endpointIPEmpty'), count: (count) => t('endpointIPCount', { count }),
    statuses: statuses.map((value) => ({ value, label: t(value) })), identity: (row) => row.address,
    value: (row, column) => 'status' in row ? column === 'status' ? t(row.status) : row.dns_name || translate('collections.missing') : '',
    load: (client, workspace, query, signal) => client.addressCollection(workspace, query, signal), read: (client, workspace, id, signal) => client.addressDetail(workspace, id, signal),
  },
  mac: {
    key: 'interface_mac', feature: 'interface-mac-addresses', parentField: 'interface_id', columns: ['name'], labels: { name: t('endpointMAC') },
    title: t('endpointMACs'), back: t('endpointMACBack'), create: t('endpointMACAdd'), search: t('endpointMACSearch'), order: t('endpointMACOrder'), failed: t('endpointMACFailed'), empty: t('endpointMACEmpty'), count: (count) => t('endpointMACCount', { count }),
    statuses: [], identity: (row) => row.address, value: () => '',
    load: (client, workspace, query, signal) => client.macCollection(workspace, query, signal), read: (client, workspace, id, signal) => client.macDetail(workspace, id, signal),
  },
}
export function InterfaceEndpoints({ kind, workspace, interfaceId, client, preferenceClient = browserCollectionPreferences }: { kind: Kind; workspace: WorkspaceContext; interfaceId: string; client: NetworksClient; preferenceClient?: typeof browserCollectionPreferences }) {
  return <NetworkChildCollection workspace={workspace} parentId={interfaceId} client={client} preferenceClient={preferenceClient} config={configs[kind]} RecordComponent={kind === 'ip' ? IPRecord : MACRecord} />
}
type Props = ChildRecordProps<Endpoint> & { parentId: string; workspace: WorkspaceContext; client: NetworksClient }
function IPRecord(props: Props) { return <EndpointRecord {...props} kind="ip" /> }
function MACRecord(props: Props) { return <EndpointRecord {...props} kind="mac" /> }
function EndpointRecord({ record, kind, parentId, workspace, client, canManage, onSaved, onReturn }: Props & { kind: Kind }) {
  const initial = { address: record?.address ?? '', description: record?.description ?? '', ...((record && 'status' in record) ? { status: record.status, dns_name: record.dns_name } : {}) }
  const [form, setForm] = useState(initial), [editing, setEditing] = useState(false), [removing, setRemoving] = useState(false), [moving, setMoving] = useState(false)
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  const attempt = useUnsavedChanges(editing && JSON.stringify(form) !== JSON.stringify(initial), busy, () => { setEditing(false); setForm(initial); setRemoving(false); setMoving(false) }, editing || removing)
  useEffect(() => { heading.current?.focus() }, [record?.id])
  async function save(remove = false) {
    if (busy || !record) return
    setBusy(true); setError('')
    try {
      const value = remove ? await client.assignEndpoint(workspace, kind, record.id, null, parentId) : kind === 'ip' ? await client.updateIPAddress(workspace, record.id, form) : await client.updateMACAddress(workspace, record.id, { address: form.address, description: form.description })
      setEditing(false); setRemoving(false); onSaved(value)
    } catch (caught) { setError(caught instanceof Error ? caught.message : t('endpointSaveFailed')) } finally { setBusy(false) }
  }
  if (!record) return <EndpointNew kind={kind} parentId={parentId} workspace={workspace} client={client} canManage={canManage} onSaved={onSaved} onReturn={onReturn} />
  return <>
    <button type="button" className="secondary-button" onClick={onReturn}>{configs[kind].back}</button>
    <h3 ref={heading} tabIndex={-1}>{record.address}</h3>
    {error && <p role="alert">{error}</p>}
    {moving && canManage ? <EndpointTransfer kind={kind} record={record} parentId={parentId} workspace={workspace} client={client} onSaved={onSaved} onCancel={() => setMoving(false)} /> : editing && canManage ? <form className="network-inline-editor" onSubmit={(event) => { event.preventDefault(); void save() }}><fieldset disabled={busy}>
      <label>{kind === 'ip' ? t('address') : t('endpointMAC')}<input required maxLength={kind === 'ip' ? 45 : 32} value={form.address} onChange={(event) => setForm({ ...form, address: event.target.value })} /></label>
      {kind === 'ip' && <><label>{t('addressStatus')}<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as NetworkIPAddress['status'] })}>{statuses.map((value) => <option key={value} value={value}>{t(value)}</option>)}</select></label><label>{t('dnsName')}<input maxLength={253} value={form.dns_name} onChange={(event) => setForm({ ...form, dns_name: event.target.value })} /></label></>}
      <label>{t('description')}<textarea rows={4} maxLength={4000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
      <div className="form-actions"><button type="submit" className="primary-button">{busy ? translate('common.saving') : t('endpointSave')}</button><button type="button" className="secondary-button" onClick={() => attempt(() => setEditing(false))}>{translate('common.cancel')}</button></div>
    </fieldset></form> : removing && canManage ? <section aria-label={t('endpointRemove')}><p>{t('endpointRemoveHelp')}</p><div className="form-actions"><button className="primary-button" type="button" disabled={busy} onClick={() => void save(true)}>{busy ? translate('common.saving') : t('endpointConfirmRemove')}</button><button className="secondary-button" type="button" disabled={busy} onClick={() => setRemoving(false)}>{translate('common.cancel')}</button></div></section> : <>
      {'status' in record && <dl className="record-facts"><div><dt>{t('addressStatus')}</dt><dd>{t(record.status)}</dd></div><div><dt>{t('dnsName')}</dt><dd>{record.dns_name || translate('collections.missing')}</dd></div><div><dt>{t('endpointSubnet')}</dt><dd>{record.subnet_cidr}</dd></div></dl>}
      <p className="network-notes">{record.description || t('noDescription')}</p>
      {canManage && <div className="form-actions"><button type="button" className="secondary-button" onClick={() => { setForm(initial); setError(''); setEditing(true) }}>{t('endpointEdit')}</button><button type="button" className="secondary-button" onClick={() => { setError(''); setMoving(true) }}>{t('endpointMove')}</button><button type="button" className="secondary-button" onClick={() => { setError(''); setRemoving(true) }}>{t('endpointRemove')}</button></div>}
    </>}
  </>
}
function EndpointTransfer({ kind, record, parentId, workspace, client, onSaved, onCancel }: { kind: Kind; record: Endpoint; parentId: string; workspace: WorkspaceContext; client: NetworksClient; onSaved: (record: Endpoint) => void; onCancel: () => void }) {
  type Choice = Omit<NetworkInterface, 'description'>
  const [search, setSearch] = useState(''), [draft, setDraft] = useState(''), [page, setPage] = useState(1), [reload, setReload] = useState(0)
  const [selected, setSelected] = useState<Choice | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [response, setResponse] = useState<{ key: string; value?: ListResult<Choice> } | null>(null)
  const key = `${workspace.kind}:${workspace.id}:${page}:${search}`
  const result = response?.key === key ? response : null
  const choices = result?.value?.results.filter((row) => row.id !== parentId) ?? []
  const attempt = useUnsavedChanges(Boolean(selected), busy, () => setSelected(null), true)
  useEffect(() => {
    const controller = new AbortController()
    client.interfaceCollection(workspace, { q: search, page, page_size: 25, ordering: 'name' }, controller.signal).then((value) => { if (!controller.signal.aborted) setResponse({ key, value }) }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) })
    return () => controller.abort()
  }, [workspace, client, search, page, key, reload])
  function find() { setSearch(draft); setPage(1) }
  async function save() {
    if (busy) return
    if (!selected) { setError(t('endpointMoveRequired')); return }
    setBusy(true); setError('')
    try { const value = await client.assignEndpoint(workspace, kind, record.id, selected.id, parentId); setSelected(null); onSaved(value) }
    catch (caught) { setError(caught instanceof Error ? caught.message : t('endpointSaveFailed')) } finally { setBusy(false) }
  }
  return <section aria-label={t('endpointMove')}>
    <p>{t('endpointMoveHelp')}</p>
    {error && <p role="alert">{error}</p>}
    <p>{t('endpointMoveSelected')}: <strong>{selected ? `${selected.device_name} — ${selected.name}` : t('endpointMoveChoose')}</strong></p>
    <div className="collection-search"><input type="search" maxLength={240} aria-label={t('endpointMoveSearch')} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); find() } }} /><button type="button" className="secondary-button" onClick={find}>{translate('collections.searchAction')}</button></div>
    {!result ? <p role="status">{translate('collections.loading')}</p> : !result.value ? <p role="alert">{t('endpointMoveFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
      {choices.length || selected ? <label>{t('endpointMoveChoices')}<select value={selected?.id ?? ''} onChange={(event) => { const row = choices.find((item) => item.id === event.target.value); if (row) setSelected(row); else setSelected(null) }}><option value="">{t('endpointMoveChoose')}</option>{selected && !choices.some((row) => row.id === selected.id) && <option value={selected.id}>{selected.device_name} — {selected.name}</option>}{choices.map((row) => <option key={row.id} value={row.id}>{row.device_name} — {row.name}</option>)}</select></label> : <p>{t('endpointMoveEmpty')}</p>}
      <CollectionPagination label={t('endpointMoveChoices')} page={page} pageSize={25} count={result.value.count} hasMore={result.value.has_more} onPageChange={setPage} />
    </>}
    <div className="form-actions"><button type="button" className="primary-button" disabled={busy} onClick={() => void save()}>{busy ? translate('common.saving') : t('endpointMoveSave')}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => attempt(onCancel)}>{translate('common.cancel')}</button></div>
  </section>
}
function EndpointNew(props: Omit<Props, 'record'> & { kind: Kind }) {
  const [mode, setMode] = useState<'create' | 'assign'>('create')
  return mode === 'create' ? <EndpointCreate key="create" {...props} onAssign={() => setMode('assign')} /> : <EndpointAssignment key="assign" {...props} onCreate={() => setMode('create')} />
}
function EndpointCreate({ kind, parentId, workspace, client, canManage, onSaved, onReturn, onAssign }: Omit<Props, 'record'> & { kind: Kind; onAssign: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null)
  const initial = { address: '', subnet_id: '', status: 'active' as NetworkIPAddress['status'], dns_name: '', description: '' }
  const [form, setForm] = useState(initial), [search, setSearch] = useState(''), [draft, setDraft] = useState(''), [page, setPage] = useState(1), [reload, setReload] = useState(0)
  const [selectedSubnet, setSelectedSubnet] = useState<Omit<NetworkSubnet, 'description'> | null>(null)
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [response, setResponse] = useState<{ key: string; value?: ListResult<Omit<NetworkSubnet, 'description'>> } | null>(null)
  const key = `${workspace.kind}:${workspace.id}:${page}:${search}`
  const result = response?.key === key ? response : null
  const dirty = JSON.stringify(form) !== JSON.stringify(initial)
  const attempt = useUnsavedChanges(dirty, busy, () => { setForm(initial); setSelectedSubnet(null) }, true)
  useEffect(() => { heading.current?.focus() }, [])
  useEffect(() => {
    if (kind !== 'ip' || !canManage) return
    const controller = new AbortController()
    client.subnetCollection(workspace, { q: search, page, page_size: 25, ordering: 'name' }, controller.signal).then((value) => { if (!controller.signal.aborted) setResponse({ key, value }) }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) })
    return () => controller.abort()
  }, [workspace, client, kind, search, page, key, canManage, reload])
  function find() { setSearch(draft); setPage(1) }
  async function save() {
    if (busy) return
    if (kind === 'ip' && !form.subnet_id) { setError(t('endpointSubnetRequired')); return }
    setBusy(true); setError('')
    try {
      const value = kind === 'ip'
        ? await client.createIPAddress(workspace, { address: form.address, subnet_id: form.subnet_id, interface_id: parentId, hardware_asset_id: null, status: form.status, dns_name: form.dns_name, description: form.description })
        : await client.createMACAddress(workspace, { address: form.address, interface_id: parentId, hardware_asset_id: null, description: form.description })
      setForm(initial); setSelectedSubnet(null)
      onSaved(value)
    } catch (caught) { setError(caught instanceof Error ? caught.message : t('endpointSaveFailed')) } finally { setBusy(false) }
  }
  return <>
    <button type="button" className="secondary-button" onClick={() => attempt(onReturn)}>{configs[kind].back}</button>
    <h3 ref={heading} tabIndex={-1}>{t(kind === 'ip' ? 'endpointIPCreate' : 'endpointMACCreate')}</h3>
    {error && <p role="alert">{error}</p>}
    {!canManage ? <p>{t('endpointDenied')}</p> : <form className="network-inline-editor" onSubmit={(event) => { event.preventDefault(); void save() }}><fieldset disabled={busy}>
      <label>{kind === 'ip' ? t('address') : t('endpointMAC')}<input required maxLength={kind === 'ip' ? 45 : 32} value={form.address} onChange={(event) => setForm({ ...form, address: event.target.value })} /></label>
      {kind === 'ip' && <>
        <div className="collection-search"><input type="search" maxLength={253} aria-label={t('endpointSubnetSearch')} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); find() } }} /><button type="button" className="secondary-button" onClick={find}>{translate('collections.searchAction')}</button></div>
        {!result ? <p role="status">{translate('collections.loading')}</p> : !result.value ? <p role="alert">{t('endpointSubnetFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
          {result.value.results.length || selectedSubnet ? <label>{t('endpointSubnet')}<select required value={form.subnet_id} onChange={(event) => { const subnet = result.value?.results.find((row) => row.id === event.target.value) ?? selectedSubnet; setSelectedSubnet(subnet?.id === event.target.value ? subnet : null); setForm({ ...form, subnet_id: event.target.value }) }}><option value="">{t('endpointSubnetChoose')}</option>{selectedSubnet && !result.value.results.some((row) => row.id === selectedSubnet.id) && <option value={selectedSubnet.id}>{selectedSubnet.name} ({selectedSubnet.cidr})</option>}{result.value.results.map((row) => <option key={row.id} value={row.id}>{row.name} ({row.cidr})</option>)}</select></label> : <p>{t('endpointSubnetEmpty')}</p>}
          <CollectionPagination label={t('endpointSubnetChoices')} page={page} pageSize={25} count={result.value.count} hasMore={result.value.has_more} onPageChange={setPage} />
        </>}
        <label>{t('addressStatus')}<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as NetworkIPAddress['status'] })}>{statuses.map((value) => <option key={value} value={value}>{t(value)}</option>)}</select></label>
        <label>{t('dnsName')}<input maxLength={253} value={form.dns_name} onChange={(event) => setForm({ ...form, dns_name: event.target.value })} /></label>
      </>}
      <label>{t('description')}<textarea rows={4} maxLength={4000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
      <div className="form-actions"><button type="submit" className="primary-button">{busy ? translate('common.saving') : t('endpointCreateSave')}</button><button type="button" className="secondary-button" onClick={() => attempt(onAssign)}>{t(kind === 'ip' ? 'endpointIPAssign' : 'endpointMACAssign')}</button><button type="button" className="secondary-button" onClick={() => attempt(onReturn)}>{translate('common.cancel')}</button></div>
    </fieldset></form>}
  </>
}
function EndpointAssignment({ kind, parentId, workspace, client, canManage, onSaved, onReturn, onCreate }: Omit<Props, 'record'> & { kind: Kind; onCreate: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [])
  const [search, setSearch] = useState(''), [draft, setDraft] = useState(''), [page, setPage] = useState(1), [reload, setReload] = useState(0)
  const [selected, setSelected] = useState<Summary | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [response, setResponse] = useState<{ key: string; value?: ListResult<Summary> } | null>(null)
  const key = `${workspace.kind}:${workspace.id}:${kind}:${page}:${search}`
  const result = response?.key === key ? response : null
  const attempt = useUnsavedChanges(Boolean(selected), busy, () => setSelected(null), true)
  useEffect(() => {
    if (!canManage) return
    const controller = new AbortController(), query = { q: search, page, page_size: 25, ordering: 'name', unassigned: 'true' as const }
    const request = kind === 'ip' ? client.addressCollection(workspace, query, controller.signal) : client.macCollection(workspace, query, controller.signal)
    request.then((value) => { if (!controller.signal.aborted) setResponse({ key, value }) }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) })
    return () => controller.abort()
  }, [workspace, client, kind, search, page, key, canManage, reload])
  function find() { setSearch(draft); setPage(1) }
  async function save() {
    if (busy) return
    if (!selected) { setError(t('endpointRequired')); return }
    setBusy(true); setError('')
    try { const value = await client.assignEndpoint(workspace, kind, selected.id, parentId, null); setSelected(null); onSaved(value) }
    catch (caught) { setError(caught instanceof Error ? caught.message : t('endpointSaveFailed')) } finally { setBusy(false) }
  }
  return <>
    <button type="button" className="secondary-button" onClick={() => attempt(onReturn)}>{configs[kind].back}</button><h3 ref={heading} tabIndex={-1}>{t(kind === 'ip' ? 'endpointIPAssign' : 'endpointMACAssign')}</h3>
    {error && <p role="alert">{error}</p>}
    {!canManage ? <p>{t('endpointDenied')}</p> : <form className="network-inline-editor" onSubmit={(event) => { event.preventDefault(); void save() }}><fieldset disabled={busy}>
      <p>{t('endpointAssignHelp')}</p><p>{t('endpointSelected')}: <strong>{selected?.address ?? t('endpointChoose')}</strong></p>
      <div className="collection-search"><input type="search" maxLength={240} aria-label={t('endpointSearchChoices')} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); find() } }} /><button type="button" className="secondary-button" onClick={find}>{translate('collections.searchAction')}</button></div>
      {!result ? <p role="status">{translate('collections.loading')}</p> : !result.value ? <p role="alert">{configs[kind].failed} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
        {result.value.results.length ? <label>{t('endpointChoices')}<select value={result.value.results.some((row) => row.id === selected?.id) ? selected!.id : ''} onChange={(event) => { const row = result.value?.results.find((item) => item.id === event.target.value); if (row) setSelected(row) }}><option value="">{t('endpointChoose')}</option>{result.value.results.map((row) => <option key={row.id} value={row.id}>{row.address}{'subnet_cidr' in row ? ` (${row.subnet_cidr})` : ''}</option>)}</select></label> : <p>{configs[kind].empty}</p>}
        <CollectionPagination label={t('endpointChoices')} page={page} pageSize={25} count={result.value.count} hasMore={result.value.has_more} onPageChange={setPage} />
      </>}
      <div className="form-actions"><button type="submit" className="primary-button">{busy ? translate('common.saving') : t('endpointAssignSave')}</button><button type="button" className="secondary-button" onClick={() => attempt(onCreate)}>{t(kind === 'ip' ? 'endpointIPCreate' : 'endpointMACCreate')}</button><button type="button" className="secondary-button" onClick={() => attempt(onReturn)}>{translate('common.cancel')}</button></div>
    </fieldset></form>}
  </>
}
