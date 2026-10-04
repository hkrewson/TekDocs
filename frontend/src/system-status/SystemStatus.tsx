import { RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { formatDateTime, translate } from '../i18n/localization'
import { browserSystemStatusClient } from './api'
import type { SystemDiagnostics, SystemStatusClient } from './api'

function label(value: string) {
  const labels: Record<string, Parameters<typeof translate>[0]> = {
    ready: 'systemStatus.ready',
    stale: 'systemStatus.stale',
    unavailable: 'systemStatus.unavailable',
    degraded: 'systemStatus.needsAttention',
    not_configured: 'systemStatus.notConfigured',
  }
  return translate(labels[value] ?? 'systemStatus.unavailable')
}

export function SystemStatus({ client = browserSystemStatusClient }: { client?: SystemStatusClient }) {
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [diagnostics, setDiagnostics] = useState<SystemDiagnostics | null>(null)

  async function refresh() {
    setPhase('loading')
    try {
      setDiagnostics(await client.load())
      setPhase('ready')
    } catch {
      setPhase('error')
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    client.load(controller.signal)
      .then((result) => { if (!controller.signal.aborted) { setDiagnostics(result); setPhase('ready') } })
      .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client])

  return <>
    <header className="page-header">
      <div><h1>{translate('systemStatus.heading')}</h1><p>{translate('systemStatus.intro')}</p></div>
      <button className="secondary-button" type="button" disabled={phase === 'loading'} onClick={() => { void refresh() }}>
        <RefreshCw size={16} aria-hidden="true" />{phase === 'loading' ? translate('systemStatus.checking') : translate('systemStatus.checkAgain')}
      </button>
    </header>
    <section className="content-section system-status" aria-labelledby="system-status-heading">
      <div className="section-heading"><h2 id="system-status-heading">{translate('systemStatus.services')}</h2></div>
      <p className="workspace-area-note">{translate('systemStatus.privacyHelp')}</p>
      {phase === 'loading' && !diagnostics && <p className="empty-state" role="status">{translate('systemStatus.loading')}</p>}
      {phase === 'loading' && diagnostics && <p role="status">{translate('systemStatus.refreshing')}</p>}
      {phase === 'error' && <div className="empty-state" role="alert"><p>{translate('systemStatus.loadFailed')}</p><button className="secondary-button" type="button" onClick={() => { void refresh() }}>{translate('common.retry')}</button></div>}
      {diagnostics && <>
        {diagnostics.status === 'degraded' && <p className="form-message error" role="alert">{translate('systemStatus.degraded')}</p>}
        <ol className="plain-detail-list">
          <li><div><strong>{translate('systemStatus.tekdocs')}</strong><span>{translate('systemStatus.versionSummary', { version: diagnostics.application_version })}</span></div><strong>{label('ready')}</strong></li>
          <li><div><strong>{translate('systemStatus.database')}</strong><span>{translate('systemStatus.databaseHelp')}</span></div><strong>{label(diagnostics.database)}</strong></li>
          <li><div><strong>{translate('systemStatus.diagramService')}</strong><span style={{ overflowWrap: 'anywhere' }}>{diagnostics.diagram_renderer.version ?? translate('systemStatus.notReported')}</span><span>{translate('systemStatus.capacityUsed', { used: diagnostics.diagram_renderer.queue.total, capacity: diagnostics.diagram_renderer.capacity })} · {translate('systemStatus.queueSummary', { waiting: diagnostics.diagram_renderer.queue.waiting, processing: diagnostics.diagram_renderer.queue.processing })}</span><span>{translate('systemStatus.lastDiagramCheck')}: {diagnostics.diagram_renderer.last_checked_at ? formatDateTime(new Date(diagnostics.diagram_renderer.last_checked_at)) : translate('systemStatus.notReported')}</span></div><strong>{label(diagnostics.diagram_renderer.status)}</strong></li>
          <li><div><strong>{translate('systemStatus.repositories')}</strong><span>{translate('systemStatus.repositorySummary', { healthy: diagnostics.repositories.healthy, total: diagnostics.repositories.total, attention: diagnostics.repositories.degraded + diagnostics.repositories.blocked + diagnostics.repositories.unknown })}</span><span>{translate('systemStatus.lastRepositoryCheck')}: {diagnostics.repositories.last_checked_at ? formatDateTime(new Date(diagnostics.repositories.last_checked_at)) : translate('systemStatus.notReported')}</span>{diagnostics.repositories.repair && <span>{translate('systemStatus.repositoryRepairHelp')}</span>}</div><strong>{label(diagnostics.repositories.status)}</strong></li>
        </ol>
        <section className="system-status-errors" aria-labelledby="renderer-errors-heading">
          <div className="section-heading"><h2 id="renderer-errors-heading">{translate('systemStatus.recentDiagramErrors')}</h2></div>
          {diagnostics.diagram_renderer.recent_failures.length === 0
            ? <p>{translate('systemStatus.noDiagramErrors')}</p>
            : <ol className="plain-detail-list">{diagnostics.diagram_renderer.recent_failures.map((failure, index) => <li key={`${failure.occurred_at}-${failure.code}-${index}`}><code style={{ overflowWrap: 'anywhere' }}>{failure.code}</code><time dateTime={new Date(failure.occurred_at).toISOString()}>{formatDateTime(new Date(failure.occurred_at))}</time></li>)}</ol>}
        </section>
        <p className="system-status-checked">{translate('systemStatus.checked')} <time dateTime={diagnostics.checked_at}>{formatDateTime(diagnostics.checked_at)}</time></p>
      </>}
    </section>
  </>
}
