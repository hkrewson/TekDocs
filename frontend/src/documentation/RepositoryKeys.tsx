import { useEffect, useId, useState } from 'react'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { RepositoryClient, RepositoryKeyState } from './repositoryApi'

export function RepositoryKeys({ contentId, sourceBlob, organizationId, client, bindings, invalidMetadata, disabled, onBindingsChange, onInsert, onReload, onEditingChange }: {
  contentId: string; sourceBlob: string; organizationId?: string; client: RepositoryClient
  bindings?: Record<string, string>; invalidMetadata: boolean; disabled: boolean
  onBindingsChange: (value: Record<string, string>) => void; onInsert: (value: string) => void
  onReload: () => void; onEditingChange: (value: boolean) => void
}) {
  const headingId = useId()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [name, setName] = useState('')
  const [reload, setReload] = useState(0)
  const [loaded, setLoaded] = useState<{ key: string; result?: RepositoryKeyState; error?: 'source' | 'load' } | null>(null)
  const targetIds = Object.values(bindings ?? {}).sort().join(',')
  const key = `${organizationId ?? 'msp'}:${contentId}:${sourceBlob}:${query}:${targetIds}:${reload}`
  const ready = loaded?.key === key && !!loaded.result
  const data = ready ? loaded.result : undefined
  const current = bindings ?? data?.key_bindings ?? {}
  const writable = ready && !disabled && !invalidMetadata && !data?.read_only
  const validName = /^[a-z][a-z0-9_]{0,39}$/.test(name)
  const declared = Object.hasOwn(current, name)
  useUnsavedChanges(name !== '', false, () => setName(''), name !== '')
  useEffect(() => { onEditingChange(name !== '') }, [name, onEditingChange])
  useEffect(() => () => onEditingChange(false), [onEditingChange])

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      void client.keys(contentId, organizationId, query, targetIds ? targetIds.split(',') : [], controller.signal)
        .then(result => {
          if (controller.signal.aborted) return
          setLoaded(result.source_blob === sourceBlob ? { key, result } : { key, error: 'source' })
        })
        .catch(() => { if (!controller.signal.aborted) setLoaded({ key, error: 'load' }) })
    }, 150)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, contentId, key, open, organizationId, query, sourceBlob, targetIds])

  if (!open) return <button type="button" className="secondary-button" onClick={() => setOpen(true)}>{translate('repository.keys.heading')}</button>
  const targets = new Map([...(data?.targets ?? []), ...(data?.bound_targets ?? [])].map(target => [target.id, target]))
  return <section className="document-context-panel document-keys" aria-labelledby={headingId}>
    <div className="section-heading"><h2 id={headingId}>{translate('repository.keys.heading')}</h2>
      <button type="button" className="secondary-button" disabled={name !== ''} onClick={() => setOpen(false)}>{translate('common.close')}</button>
    </div>
    {loaded?.key !== key && <p role="status">{translate('documentation.loadingKeys')}</p>}
    {loaded?.key === key && loaded.error && <div role="alert">
      <p>{translate(loaded.error === 'source' ? 'repository.keys.sourceChanged' : 'repository.keys.failed')}</p>
      <button type="button" className="secondary-button" onClick={() => setReload(value => value + 1)}>{translate('documentation.retryKeys')}</button>
      {loaded.error === 'source' && <button type="button" className="secondary-button" onClick={onReload}>{translate('repository.keys.reloadDocument')}</button>}
    </div>}
    {invalidMetadata && <p role="alert">{translate('repository.keys.invalidMetadata')}</p>}
    {Object.keys(current).length >= 64 && <p role="alert">{translate('repository.keys.bindingLimit')}</p>}
    {data?.read_only && <p>{translate('documentation.readOnlyBindings')}</p>}
    <label>{translate('repository.keys.bindingName')}<input value={name} disabled={disabled || data?.read_only || invalidMetadata} onChange={event => setName(event.target.value.toLowerCase())} placeholder="subject" aria-invalid={name !== '' && (!validName || declared)} aria-describedby={name ? headingId + '-name-rule' : undefined} /></label>
    {name && <><p id={headingId + '-name-rule'} className="field-hint">{translate(declared ? 'repository.keys.nameUsed' : 'documentation.bindingNameRule')}</p>
      <button type="button" className="secondary-button" onClick={() => setName('')}>{translate('repository.keys.cancelBinding')}</button></>}
    <label>{translate('repository.keys.search')}<input type="search" value={query} maxLength={120} disabled={disabled} onChange={event => setQuery(event.target.value)} /></label>
    {data && <>
      <ul>{data.targets.map(target => <li key={target.id}><span><strong>{target.title}</strong><small>{target.kind === 'fragment' ? translate('repository.fragment') : target.entity_type.replaceAll('_', ' ')}</small></span>
        <div className="form-actions"><button type="button" className="secondary-button" disabled={!writable || !validName || declared || target.fields.length === 0 || Object.keys(current).length >= 64} onClick={() => { onBindingsChange({ ...current, [name]: target.id }); setName('') }} aria-label={translate('repository.keys.bindTarget', { title: target.title })}>{translate('repository.keys.bind')}</button>
          {target.kind === 'entity' && <button type="button" className="secondary-button" disabled={!writable} onClick={() => onInsert(`<tekdocs://entity/${target.id}>`)} aria-label={translate('repository.keys.referenceTarget', { title: target.title })}>{translate('repository.keys.reference')}</button>}</div>
      </li>)}</ul>
      {data.targets.length === 0 && <p>{translate('repository.keys.noTargets')}</p>}
      {data.has_more && <p>{translate('repository.keys.refineSearch')}</p>}
      <ul aria-label={translate('documentation.keyBindingsTable')}>{Object.entries(current).map(([binding, id]) => <li key={binding}>
        <span><strong>{binding}</strong><small>{targets.get(id)?.title ?? translate('repository.keys.unavailable')}</small></span>
        <div className="form-actions"><label htmlFor={headingId + '-field-' + binding}>{translate('repository.keys.insertFor', { name: binding })}</label><select id={headingId + '-field-' + binding} defaultValue="" disabled={!writable || !targets.get(id)?.fields.length} onChange={event => { if (event.target.value) { onInsert(`<tekdocs://key/${binding}.${event.target.value}>`); event.target.value = '' } }}>
          <option value="">{translate('documentation.insertKey')}</option>{targets.get(id)?.fields.map(field => <option key={field} value={field}>{field}</option>)}</select>
          <button type="button" className="secondary-button" disabled={!writable} onClick={() => onBindingsChange(Object.fromEntries(Object.entries(current).filter(([key]) => key !== binding)))} aria-label={translate('repository.keys.removeNamed', { name: binding })}>{translate('repository.keys.remove')}</button></div>
      </li>)}</ul>
      {Object.keys(current).length === 0 && <p>{translate('repository.keys.empty')}</p>}
      <div role="group" aria-label={translate('documentation.keyReportTable')}><h3>{translate('repository.keys.savedReport')}</h3>
        <ul>{data.report.map(row => <li key={row.expression}><strong>{row.expression}</strong><small>{translate(`repository.keys.state.${row.state}`)}</small></li>)}</ul>
        {data.report.length === 0 && <p>{translate('repository.keys.noExpressions')}</p>}
        {data.report_has_more && <p>{translate('repository.keys.reportLimit')}</p>}
      </div>
    </>}
  </section>
}
