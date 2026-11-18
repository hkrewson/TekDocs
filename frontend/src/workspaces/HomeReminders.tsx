import { Plus } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { formatPlainDate, translate } from '../i18n/localization'
import { browserOperationsClient } from '../operations/api'
import type { OperationsClient, ReminderRecord } from '../operations/api'
import type { WorkspaceContext } from './api'
import { organizationWorkspacePath } from './navigation'

type ReminderState = { key: string; reminders: ReminderRecord[] }

export function HomeReminders({ workspace, client = browserOperationsClient, primaryAction = true }: { workspace: WorkspaceContext | null; client?: OperationsClient; primaryAction?: boolean }) {
  const scope = useMemo(() => workspace ? { organizationId: workspace.id } : {}, [workspace])
  const workspaceKey = workspace?.id ?? 'msp'
  const remindersPath = workspace ? organizationWorkspacePath(workspace, 'deadlines') : '/deadlines'
  const [revision, setRevision] = useState(0)
  const [loaded, setLoaded] = useState<ReminderState | null>(null)
  const [failureKey, setFailureKey] = useState<string | null>(null)
  const requestKey = `${workspaceKey}:${revision}`
  const reminders = loaded?.key === requestKey ? loaded.reminders : null
  const failed = failureKey === requestKey

  useEffect(() => {
    const controller = new AbortController()
    client.reminders(scope, controller.signal).then((results) => {
      if (!controller.signal.aborted) {
        const active = results.filter((reminder) => reminder.active).sort((left, right) => left.due_on.localeCompare(right.due_on)).slice(0, 8)
        setLoaded({ key: requestKey, reminders: active })
        setFailureKey(null)
      }
    }).catch(() => { if (!controller.signal.aborted) setFailureKey(requestKey) })
    return () => controller.abort()
  }, [client, requestKey, scope])

  return <section className="content-section home-reminders" aria-labelledby={`home-reminders-heading-${workspaceKey}`}>
    <div className="section-heading">
      <div><h2 id={`home-reminders-heading-${workspaceKey}`}>{translate('overview.reminders')}</h2><p>{translate('overview.remindersHelp')}</p></div>
      <div className="home-reminder-actions"><Link className={`${primaryAction ? 'primary-button' : 'secondary-button'} compact-button`} to={`${remindersPath}?new=1`}><Plus size={15} aria-hidden="true" />{translate('overview.newReminder')}</Link><Link to={remindersPath}>{translate('overview.allReminders')}</Link></div>
    </div>
    {!reminders && !failed && <p role="status">{translate('overview.remindersLoading')}</p>}
    {failed && <div role="alert" className="home-reminder-error"><p>{translate('overview.remindersUnavailable')}</p><button type="button" className="secondary-button compact-button" onClick={() => setRevision((value) => value + 1)}>{translate('common.retry')}</button></div>}
    {reminders?.length === 0 && <p className="empty-state">{translate('overview.nothingDue')}</p>}
    {reminders && reminders.length > 0 && <ol className="plain-detail-list home-reminder-list">{reminders.map((reminder) => <li key={reminder.id}><div><strong>{reminder.title}</strong><span>{reminder.source}</span></div><time dateTime={reminder.due_on}>{formatPlainDate(reminder.due_on)}</time></li>)}</ol>}
  </section>
}
