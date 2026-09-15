import { useState } from 'react'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { ChildRecordProps } from './NetworkChildCollection'
import { CircuitChoice } from './CircuitChoice'
import type { CircuitChoiceValue } from './CircuitChoice'
import type { CircuitDetail, NetworksClient } from './api'
import { networkText as t } from './networkText'
export function CircuitEditor({ record, workspace, client, onSaved, onCancel }: ChildRecordProps<CircuitDetail> & { workspace: WorkspaceContext; client: NetworksClient; onCancel: () => void }) {
  const initialProvider = record ? { id: record.provider_id, name: record.provider_name } : null
  const initialContract = record?.contract ? { id: record.contract.id, name: record.contract.name } : null
  const [provider, setProvider] = useState<CircuitChoiceValue | null>(initialProvider), [contract, setContract] = useState<CircuitChoiceValue | null>(initialContract)
  const [name, setName] = useState(''), [identifier, setIdentifier] = useState(''), [description, setDescription] = useState(''), [kind, setKind] = useState<CircuitDetail['kind']>('internet')
  const [complete, setComplete] = useState(false)
  const [allowed, setAllowed] = useState<boolean | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const changed = provider?.id !== initialProvider?.id || contract?.id !== initialContract?.id || Boolean(name || identifier || description) || kind !== 'internet'
  const attempt = useUnsavedChanges(changed && !complete, busy, onCancel, !complete)
  // A missing contract property denotes restricted projection. Never offer a
  // provider change that could implicitly expose or replace a hidden contract.
  const restricted = Boolean(record && !('contract' in record))
  async function save() {
    if (!provider || busy) return
    setBusy(true); setError('')
    try {
      const saved = record ? await client.updateCircuit(workspace, record.id, {
        ...(provider.id !== record.provider_id ? { provider_id: provider.id } : {}),
        ...(allowed ? { contract_id: contract?.id ?? null } : {}),
      }) : await client.createCircuit(workspace, {
        name, service_identifier: identifier, description, provider_id: provider.id, contract_id: allowed ? contract?.id ?? null : null,
        kind, status: 'ordered', bandwidth_down_mbps: null, bandwidth_up_mbps: null, installed_on: null, service_starts_on: null, review_on: null, planned_disconnect_on: null,
      })
      setComplete(true); onSaved(saved); if (record) onCancel()
    } catch (caught) { setError(caught instanceof Error ? caught.message : t('circuitSaveFailed')) } finally { setBusy(false) }
  }
  return <form className="network-inline-editor" onSubmit={event => { event.preventDefault(); void save() }}>
    <h2>{record ? t('circuitAssignmentEdit') : t('circuitNew')}</h2>{error && <p role="alert">{error}</p>}
    <fieldset disabled={busy}>
      {!record && <><div className="field-grid"><label>{t('name')}<input required maxLength={240} value={name} onChange={event => setName(event.target.value)} /></label><label>{t('circuitIdentifier')}<input required maxLength={240} value={identifier} onChange={event => setIdentifier(event.target.value)} /></label><label>{t('circuitKind')}<select value={kind} onChange={event => setKind(event.target.value as CircuitDetail['kind'])}>{(['internet', 'wan', 'mpls', 'dark_fiber', 'broadband', 'cellular', 'voice', 'other'] as const).map(value => <option key={value} value={value}>{t(`circuitValue_${value}`)}</option>)}</select></label></div><p>{t('circuitCreateStatus')}</p></>}
      {restricted ? <p>{t('circuitAssignmentRestricted')}</p> : <CircuitChoice kind="providers" selected={provider} workspace={workspace} client={client} onPermission={setAllowed} onChange={value => { setProvider(value); if (value.id !== provider?.id) setContract(null) }} />}
      {!restricted && allowed && provider && <><CircuitChoice key={provider.id} kind="contracts" selected={contract} providerId={provider.id} workspace={workspace} client={client} onChange={setContract} /><button type="button" className="secondary-button" disabled={!contract} onClick={() => setContract(null)}>{t('circuitContractClear')}</button></>}
      {record && <p>{t('circuitAssignmentReview')}</p>}
      {!record && <label>{t('description')}<textarea rows={4} maxLength={4000} value={description} onChange={event => setDescription(event.target.value)} /></label>}
      <div className="form-actions"><button className="primary-button" disabled={!provider || restricted || allowed === null || Boolean(record && !changed)}>{busy ? translate('common.saving') : record ? t('circuitAssignmentSave') : t('circuitCreate')}</button><button type="button" className="secondary-button" onClick={() => attempt(onCancel)}>{translate('common.cancel')}</button></div>
    </fieldset>
  </form>
}
