import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { formatPlainDate, translate } from '../i18n/localization'
import { browserOperationsClient } from '../operations/api'
import type { OperationsClient, ReminderRecord } from '../operations/api'
import { browserWorkspaceClient } from './api'
import type { WorkspaceClient } from './api'

type HomeState = { organizations: number; reminders: ReminderRecord[] }

export default function Overview({ workspaceClient = browserWorkspaceClient, operationsClient = browserOperationsClient }: { workspaceClient?: WorkspaceClient; operationsClient?: OperationsClient }) {
  const [state, setState] = useState<HomeState | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      workspaceClient.searchOrganizations('', 1, controller.signal),
      operationsClient.reminders({}, controller.signal),
    ]).then(([organizations, reminders]) => {
      if (!controller.signal.aborted) {
        setState({ organizations: organizations.results.length, reminders: reminders.filter((item) => item.active).slice(0, 8) })
        setFailed(false)
      }
    }).catch(() => { if (!controller.signal.aborted) setFailed(true) })
    return () => controller.abort()
  }, [operationsClient, workspaceClient])

  return <>
    <header className="page-header"><div><h1>{translate('overview.heading')}</h1></div></header>
    {state?.organizations === 0 && <section className="content-section overview-setup" aria-labelledby="overview-setup-heading">
      <div className="section-heading"><h2 id="overview-setup-heading">{translate('overview.setup')}</h2></div>
      <p>{translate('overview.setupOrganizations')}</p>
      <Link className="primary-button compact-button" to="/organizations">{translate('overview.addOrganization')}</Link>
    </section>}
    <section className="content-section" aria-labelledby="overview-work-heading">
      <div className="section-heading"><h2 id="overview-work-heading">{translate('overview.workQueue')}</h2><Link to="/deadlines">{translate('overview.allReminders')}</Link></div>
      {!state && !failed && <p role="status">{translate('common.loading')}</p>}
      {failed && <p role="status">{translate('overview.unavailable')}</p>}
      {state && state.reminders.length === 0 && <p className="empty-state">{translate('overview.nothingDue')}</p>}
      {state && state.reminders.length > 0 && <ol className="plain-detail-list">{state.reminders.map((reminder) => <li key={reminder.id}><div><strong>{reminder.title}</strong><span>{reminder.source}</span></div><time dateTime={reminder.due_on}>{formatPlainDate(reminder.due_on)}</time></li>)}</ol>}
    </section>
  </>
}
