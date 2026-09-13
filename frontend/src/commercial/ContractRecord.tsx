import { useEffect, useState } from 'react'
import { RecordHeader, RecordSections } from '../records/RecordNavigation'
import { RecordActivity } from '../records/RecordActivity'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import { browserRelationshipsClient } from '../relationships/api'
import type { EntityRelationship } from '../relationships/api'
import type { WorkspaceContext } from '../workspaces/api'
import type { CommercialClient, CommercialContract, ContractCost } from './api'
import { ContractEditor, CostEditor } from './ContractForms'
import { blankContract, blankCost, contractForm, costForm, dates } from './contractValues'
import { translate } from '../i18n/localization'
import { contractText as t } from './contractText'

export function ContractRecord({ record, workspace, client, canManage, canViewCosts, canViewRelationships, section, href, embedded, onChange, onArchive }: {
  record: CommercialContract; workspace: WorkspaceContext; client: CommercialClient; canManage: boolean; canViewCosts: boolean; canViewRelationships: boolean; section: string; href: (section: string) => string; embedded: boolean; onChange: (record: CommercialContract) => void; onArchive: () => void
}) {
  const [mode, setMode] = useState<'none' | 'edit' | 'cost' | 'edit-cost'>('none')
  const [contract, setContract] = useState(() => contractForm(record))
  const [cost, setCost] = useState(blankCost)
  const [costId, setCostId] = useState<string | null>(null)
  const [confirmation, setConfirmation] = useState<'archive' | ContractCost | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const dirty = mode === 'edit' ? JSON.stringify(contract) !== JSON.stringify(contractForm(record)) : mode !== 'none' && JSON.stringify(cost) !== JSON.stringify(mode === 'edit-cost' ? costForm(record.costs!.find((item) => item.id === costId)!) : blankCost)
  const attempt = useUnsavedChanges(dirty, busy, () => { setMode('none'); setConfirmation(null) }, mode !== 'none' || confirmation !== null)
  const tabs: Array<'overview' | 'costs' | 'related' | 'history'> = ['overview', 'costs', ...(canViewRelationships ? ['related' as const] : []), 'history']
  const current = tabs.find((tab) => tab === section) ?? 'overview'
  const providers = useProviders(workspace, client, mode === 'edit')
  async function perform(action: () => Promise<CommercialContract>) {
    setBusy(true); setError(null)
    try { onChange(await action()); setMode('none'); setConfirmation(null) }
    catch (caught) { setError(caught instanceof Error ? caught.message : t('changeFailed')) }
    finally { setBusy(false) }
  }
  async function archive() {
    setBusy(true); setError(null)
    try { await client.archiveContract(workspace, record.id); setConfirmation(null); onArchive() }
    catch (caught) { setError(caught instanceof Error ? caught.message : t('archiveFailed')) }
    finally { setBusy(false) }
  }
  const today = new Date().toISOString().slice(0, 10)
  return <article className="record-page contract-record">
    {!embedded && <RecordHeader recordId={record.id} section={current} title={record.name} description={record.provider_name} />}
    <RecordSections current={current} sections={tabs.map((id) => ({ id, label: translate(`collections.${id}`), href: href(id) }))} />
    {error && <p role="alert">{error}</p>}
    <section key={current} aria-label={translate(`collections.${current}`)}>
      {current === 'overview' && <>
        {(record.status === 'expired' || (record.renews_on && record.renews_on < today)) && <p role="status">{t('warning')}</p>}
        {mode === 'edit' ? <>{providers.error && <p role="alert">{t('providerFailed')} <button type="button" onClick={providers.retry}>{translate('collections.retry')}</button></p>}<ContractEditor title={t('editTitle', { name: record.name })} value={contract} setValue={setContract} providers={providers.items} canSubmit={providers.ready} busy={busy} cancel={() => attempt(() => setMode('none'))} submit={() => { if (providers.ready) void perform(() => client.updateContract(workspace, record.id, { ...dates(contract), renews_on: contract.renews_on || null })) }} /></> : <>
          <p>{record.description || t('noDescription')}</p>
          <dl className="record-facts"><Fact label={t('provider')} value={record.provider_name} /><Fact label={t('status')} value={record.status} /><Fact label={t('kind')} value={record.kind} /><Fact label={t('term')} value={t('termValue', { start: record.starts_on || t('open'), end: record.ends_on || t('open') })} /><Fact label={t('renewal')} value={record.auto_renew ? t('autoRenewValue', { date: record.renews_on || t('unscheduled') }) : record.renews_on || t('unscheduled')} /><Fact label={t('notice')} value={record.renewal_notice_days ? t('days', { days: record.renewal_notice_days }) : t('none')} /><Fact label={t('reference')} value={record.reference || translate('collections.missing')} /></dl>
          {canManage && <div className="form-actions"><button type="button" className="secondary-button" onClick={() => attempt(() => { setContract(contractForm(record)); setMode('edit') })}>{translate('commercial.editContract')}</button><button type="button" className="secondary-button" onClick={() => attempt(() => setConfirmation('archive'))}>{translate('common.archive')}</button></div>}
        </>}
      </>}
      {current === 'costs' && <>
        <h2>{translate('collections.costs')}</h2>
        {!canViewCosts ? <p>{t('costsDenied')}</p> : <>
          <p>{t('costsHelp')}</p>
          {mode === 'cost' || mode === 'edit-cost' ? <CostEditor title={t(mode === 'cost' ? 'addCostTitle' : 'editCostTitle')} submitLabel={mode === 'cost' ? translate('commercial.addCost') : t('saveCost')} value={cost} setValue={setCost} busy={busy} cancel={() => attempt(() => setMode('none'))} submit={() => void perform(() => mode === 'cost' ? client.createCost(workspace, record.id, dates(cost)) : client.updateCost(workspace, record.id, costId!, dates(cost)))} /> : <>
            {canManage && <button type="button" className="secondary-button" onClick={() => attempt(() => { setCost(blankCost); setMode('cost') })}>{translate('commercial.addCost')}</button>}
            {record.costs?.length ? <ul className="contract-costs">{record.costs.map((item) => <li key={item.id}><strong>{item.label}</strong><p>{t('costValue', { currency: item.currency, amount: item.amount, quantity: item.quantity, interval: item.billing_interval.replaceAll('_', ' ') })}</p>{canManage && <div className="form-actions"><button type="button" className="text-button" aria-label={t('editCost', { name: item.label })} onClick={() => attempt(() => { setCost(costForm(item)); setCostId(item.id); setMode('edit-cost') })}>{translate('common.edit')}</button><button type="button" className="text-button" aria-label={t('removeCost', { name: item.label })} onClick={() => attempt(() => setConfirmation(item))}>{translate('common.remove')}</button></div>}</li>)}</ul> : <p>{t('costsEmpty')}</p>}
          </>}
        </>}
      </>}
      {current === 'related' && canViewRelationships && <ContractRelated workspace={workspace} id={record.id} />}
      {current === 'history' && <RecordActivity entityId={record.id} workspace={workspace} description={t('historyHelp')} emptyLabel={t('historyEmpty')} deniedLabel={t('historyDenied')} actionLabels={{ 'commercial_contract.created': t('contractCreated'), 'commercial_contract.updated': t('contractUpdated'), 'commercial_contract.cost_created': t('costCreated'), 'commercial_contract.cost_updated': t('costUpdated'), 'commercial_contract.cost_archived': t('costArchived') }} />}
      {confirmation && <div className="archive-confirmation" role="alertdialog" aria-labelledby="contract-confirmation"><strong id="contract-confirmation">{translate(confirmation === 'archive' ? 'contracts.archiveHeading' : 'contracts.removeCostHeading', { name: confirmation === 'archive' ? record.name : confirmation.label })}</strong><p>{translate(confirmation === 'archive' ? 'contracts.archiveHelp' : 'contracts.removeCostHelp')}</p><div className="form-actions"><button type="button" className="danger-button" disabled={busy} onClick={() => { if (confirmation === 'archive') void archive(); else void perform(() => client.archiveCost(workspace, record.id, confirmation.id)) }}>{translate(confirmation === 'archive' ? 'common.archive' : 'common.remove')}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => setConfirmation(null)}>{translate('common.cancel')}</button></div></div>}
    </section>
  </article>
}

function Fact({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div> }

function useProviders(workspace: WorkspaceContext, client: CommercialClient, enabled: boolean) {
  const [state, setState] = useState<{ items: Array<{ id: string; name: string }>; ready: boolean; error: boolean }>({ items: [], ready: false, error: false })
  const [reload, setReload] = useState(0)
  useEffect(() => { if (!enabled) return; const controller = new AbortController(); client.providerChoices(workspace, controller.signal).then((value) => { if (!controller.signal.aborted) setState({ items: value.results, ready: true, error: false }) }).catch(() => { if (!controller.signal.aborted) setState({ items: [], ready: false, error: true }) }); return () => controller.abort() }, [client, workspace, enabled, reload])
  return { ...state, retry: () => setReload(reload + 1) }
}

export function ContractCreate({ workspace, client, onCreated, onCancel }: { workspace: WorkspaceContext; client: CommercialClient; onCreated: (record: CommercialContract) => void; onCancel: () => void }) {
  const [form, setForm] = useState(blankContract)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const providers = useProviders(workspace, client, true)
  const attempt = useUnsavedChanges(JSON.stringify(form) !== JSON.stringify(blankContract), busy, () => setForm(blankContract), true)
  async function save() { if (!providers.ready) return; setBusy(true); setError(null); try { const created = await client.createContract(workspace, { ...dates(form), renews_on: form.renews_on || null }); setForm(blankContract); onCreated(created) } catch (caught) { setError(caught instanceof Error ? caught.message : t('changeFailed')) } finally { setBusy(false) } }
  return <>{error && <p role="alert">{error}</p>}{providers.error && <p role="alert">{t('providerFailed')} <button type="button" onClick={providers.retry}>{translate('collections.retry')}</button></p>}<ContractEditor title={translate('contracts.new')} value={form} setValue={setForm} providers={providers.items} canSubmit={providers.ready} busy={busy} cancel={() => attempt(onCancel)} submit={() => void save()} /></>
}

function ContractRelated({ workspace, id }: { workspace: WorkspaceContext; id: string }) {
  const [items, setItems] = useState<EntityRelationship[] | null>(null)
  const [error, setError] = useState(false)
  const [reload, setReload] = useState(0)
  useEffect(() => { const controller = new AbortController(); browserRelationshipsClient.list(workspace.kind === 'organization' ? { organizationId: workspace.id } : {}, id, controller.signal).then((result) => { if (!controller.signal.aborted) setItems(result) }).catch(() => { if (!controller.signal.aborted) setError(true) }); return () => controller.abort() }, [id, workspace, reload])
  return <><h2>{translate('collections.related')}</h2>{error ? <p role="alert">{t('relatedFailed')} <button type="button" onClick={() => { setError(false); setReload(reload + 1) }}>{translate('collections.retry')}</button></p> : !items ? <p role="status">{translate('collections.loading')}</p> : items.length ? <ul>{items.map((item) => <li key={item.id}>{item.label} · {item.related_entity.display_name} · {item.related_entity.entity_type.replaceAll('_', ' ')}</li>)}</ul> : <p>{t('relatedEmpty')}</p>}</>
}
