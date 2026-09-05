import { RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { formatDateTime, translate } from '../i18n/localization'
import { browserSystemStatusClient } from './api'
import type { SystemDiagnostics, SystemStatusClient } from './api'

function label(value: string) {
  return value === 'ready' ? translate('systemStatus.ready') : value.replaceAll('_', ' ')
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
      <div><h1>{translate('systemStatus.heading')}</h1></div>
      <button className="secondary-button" type="button" disabled={phase === 'loading'} onClick={() => { void refresh() }}>
        <RefreshCw size={16} aria-hidden="true" />{phase === 'loading' ? translate('systemStatus.checking') : translate('systemStatus.checkAgain')}
      </button>
    </header>
    <section className="content-section system-status" aria-labelledby="system-status-heading">
      <div className="section-heading"><h2 id="system-status-heading">{translate('systemStatus.services')}</h2></div>
      <p className="workspace-area-note">{translate('systemStatus.privacyHelp')}</p>
      {phase === 'loading' && !diagnostics && <p role="status">{translate('systemStatus.loading')}</p>}
      {phase === 'error' && <p role="alert">{translate('systemStatus.loadFailed')}</p>}
      {diagnostics && <>
        <dl className="system-status-list">
          <div><dt>{translate('systemStatus.tekdocs')}</dt><dd>{diagnostics.application_version}</dd></div>
          <div><dt>{translate('systemStatus.database')}</dt><dd>{label(diagnostics.database)}</dd></div>
          <div><dt>{translate('systemStatus.diagramService')}</dt><dd>{label(diagnostics.diagram_renderer.status)}</dd></div>
          <div><dt>{translate('systemStatus.diagramServiceVersion')}</dt><dd>{diagnostics.diagram_renderer.version ?? translate('systemStatus.notReported')}</dd></div>
          <div><dt>{translate('systemStatus.diagramJobs')}</dt><dd>{translate('systemStatus.capacityUsed', { used: diagnostics.diagram_renderer.queue.total, capacity: diagnostics.diagram_renderer.capacity })}</dd></div>
          <div><dt>{translate('systemStatus.waiting')}</dt><dd>{diagnostics.diagram_renderer.queue.waiting}</dd></div>
          <div><dt>{translate('systemStatus.processing')}</dt><dd>{diagnostics.diagram_renderer.queue.processing}</dd></div>
          <div><dt>{translate('systemStatus.lastDiagramCheck')}</dt><dd>{diagnostics.diagram_renderer.last_checked_at ? formatDateTime(new Date(diagnostics.diagram_renderer.last_checked_at)) : translate('systemStatus.notReported')}</dd></div>
        </dl>
        <section className="system-status-errors" aria-labelledby="renderer-errors-heading">
          <div className="section-heading"><h2 id="renderer-errors-heading">{translate('systemStatus.recentDiagramErrors')}</h2></div>
          {diagnostics.diagram_renderer.recent_failures.length === 0
            ? <p>{translate('systemStatus.noDiagramErrors')}</p>
            : <div className="table-scroll" role="group" aria-label={translate('systemStatus.rendererErrorsTable')} tabIndex={0}><table><thead><tr><th>{translate('systemStatus.code')}</th><th>{translate('systemStatus.occurred')}</th></tr></thead><tbody>{diagnostics.diagram_renderer.recent_failures.map((failure, index) => <tr key={`${failure.occurred_at}-${failure.code}-${index}`}><td><code>{failure.code}</code></td><td><time dateTime={new Date(failure.occurred_at).toISOString()}>{formatDateTime(new Date(failure.occurred_at))}</time></td></tr>)}</tbody></table></div>}
        </section>
        <p className="system-status-checked">{translate('systemStatus.checked')} <time dateTime={diagnostics.checked_at}>{formatDateTime(diagnostics.checked_at)}</time></p>
      </>}
    </section>
  </>
}
