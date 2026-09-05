import { RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { formatDateTime, translate } from '../i18n/localization'
import { browserSystemStatusClient } from './api'
import type { SystemDiagnostics, SystemStatusClient } from './api'

function label(value: string) {
  return value.replaceAll('_', ' ')
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
      <div><h1>System status</h1></div>
      <button className="secondary-button" type="button" disabled={phase === 'loading'} onClick={() => { void refresh() }}>
        <RefreshCw size={16} aria-hidden="true" />{phase === 'loading' ? 'Checking…' : 'Check again'}
      </button>
    </header>
    <section className="content-section system-status" aria-labelledby="system-status-heading">
      <div className="section-heading"><h2 id="system-status-heading">Services</h2></div>
      <p className="workspace-area-note">This view excludes document content, file paths, and renderer output.</p>
      {phase === 'loading' && !diagnostics && <p role="status">Checking system status…</p>}
      {phase === 'error' && <p role="alert">System status could not be loaded.</p>}
      {diagnostics && <>
        <dl className="system-status-list">
          <div><dt>TekDocs</dt><dd>{diagnostics.application_version}</dd></div>
          <div><dt>Database</dt><dd>{label(diagnostics.database)}</dd></div>
          <div><dt>Diagram renderer</dt><dd>{label(diagnostics.diagram_renderer.status)}</dd></div>
          <div><dt>Renderer version</dt><dd>{diagnostics.diagram_renderer.version ?? 'Not reported'}</dd></div>
          <div><dt>Queue</dt><dd>{diagnostics.diagram_renderer.queue.total} of {diagnostics.diagram_renderer.capacity} slots in use</dd></div>
          <div><dt>Waiting</dt><dd>{diagnostics.diagram_renderer.queue.waiting}</dd></div>
          <div><dt>Processing</dt><dd>{diagnostics.diagram_renderer.queue.processing}</dd></div>
          <div><dt>Last renderer check</dt><dd>{diagnostics.diagram_renderer.last_checked_at ? formatDateTime(new Date(diagnostics.diagram_renderer.last_checked_at)) : 'Not reported'}</dd></div>
        </dl>
        <section className="system-status-errors" aria-labelledby="renderer-errors-heading">
          <div className="section-heading"><h2 id="renderer-errors-heading">Recent renderer errors</h2></div>
          {diagnostics.diagram_renderer.recent_failures.length === 0
            ? <p>No recent renderer errors.</p>
            : <div className="table-scroll" role="group" aria-label={translate('systemStatus.rendererErrorsTable')} tabIndex={0}><table><thead><tr><th>Code</th><th>Occurred</th></tr></thead><tbody>{diagnostics.diagram_renderer.recent_failures.map((failure, index) => <tr key={`${failure.occurred_at}-${failure.code}-${index}`}><td><code>{failure.code}</code></td><td><time dateTime={new Date(failure.occurred_at).toISOString()}>{formatDateTime(new Date(failure.occurred_at))}</time></td></tr>)}</tbody></table></div>}
        </section>
        <p className="system-status-checked">Checked <time dateTime={diagnostics.checked_at}>{formatDateTime(diagnostics.checked_at)}</time></p>
      </>}
    </section>
  </>
}
