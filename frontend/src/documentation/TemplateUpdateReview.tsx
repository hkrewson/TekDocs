import { useEffect, useRef } from 'react'
import { translate } from '../i18n/localization'
import type { TemplatePlacementMode, TemplateRollout } from './api'

export function TemplateUpdateReview({ rollout, rules, busy, onRule, onApply, onClose }: { rollout: TemplateRollout; rules: Record<string, TemplatePlacementMode>; busy: boolean; onRule: (id: string, mode: TemplatePlacementMode) => void; onApply: () => void; onClose: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus(); heading.current?.scrollIntoView?.({ block: 'nearest' }) }, [])
  return <section className="document-context-panel template-rollout" aria-labelledby="template-update-heading">
    <div className="section-heading"><div><h2 ref={heading} tabIndex={-1} id="template-update-heading">{translate('documentation.templateUpdates')}</h2><p>{translate('documentation.templateVersionStatus', { current: rollout.current_revision, available: rollout.available_revision })}</p></div><button type="button" className="secondary-button" disabled={busy} onClick={onClose}>{translate('documentation.closeTemplateUpdates')}</button></div>
    {rollout.up_to_date ? <p>{translate('documentation.templateCurrent')}</p> : <>
      {rollout.conflicts.length > 0 && <div role="alert"><h3>{translate('documentation.templateConflicts')}</h3><p>{translate('documentation.templateConflictHelp')}</p><ul>{rollout.conflicts.map((item) => <li key={item.source_block_id}><strong>{item.name}</strong><p>{item.reason}</p></li>)}</ul></div>}
      {(['added', 'changed', 'removed'] as const).map((kind) => rollout[kind].length > 0 && <section key={kind} aria-label={translate(`documentation.template${kind}`)}><h3>{translate(`documentation.template${kind}`)}</h3><ul className="template-section-choices">{rollout[kind].map((item) => <li key={item.source_block_id}><strong>{item.name}</strong>{kind === 'added' ? <label>{translate('documentation.templateSectionBehavior', { name: item.name })}<select disabled={busy} value={rules[item.source_block_id] ?? 'copy'} onChange={(event) => onRule(item.source_block_id, event.target.value as TemplatePlacementMode)}><option value="copy">{translate('documentation.templateCopyOnce')}</option><option value="live">{translate('documentation.templateKeepUpdated')}</option><option value="pinned">{translate('documentation.templateKeepVersion')}</option></select></label> : item.mode && <p>{translate(item.mode === 'live' ? 'documentation.templateKeepUpdated' : item.mode === 'pinned' ? 'documentation.templateKeepVersion' : 'documentation.templateCopyOnce')}</p>}</li>)}</ul></section>)}
      <p>{translate('documentation.templateBehaviorHelp')}</p>
      <button className="primary-button" type="button" disabled={busy || rollout.conflicts.length > 0} onClick={onApply}>{translate('documentation.applySafeChanges')}</button>
    </>}
  </section>
}
