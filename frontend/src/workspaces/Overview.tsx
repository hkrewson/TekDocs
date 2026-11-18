import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { translate } from '../i18n/localization'
import { browserOperationsClient } from '../operations/api'
import type { OperationsClient } from '../operations/api'
import { browserWorkspaceClient } from './api'
import type { WorkspaceClient } from './api'
import { HomeReminders } from './HomeReminders'

export default function Overview({ workspaceClient = browserWorkspaceClient, operationsClient = browserOperationsClient }: { workspaceClient?: WorkspaceClient; operationsClient?: OperationsClient }) {
  const [organizationCount, setOrganizationCount] = useState<number | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    workspaceClient.searchOrganizations('', 1, controller.signal)
      .then((organizations) => { if (!controller.signal.aborted) setOrganizationCount(organizations.results.length) })
      .catch(() => { if (!controller.signal.aborted) setOrganizationCount(null) })
    return () => controller.abort()
  }, [workspaceClient])

  return <>
    <header className="page-header"><div><h1>{translate('overview.heading')}</h1></div></header>
    {organizationCount === 0 && <section className="content-section overview-setup" aria-labelledby="overview-setup-heading">
      <div className="section-heading"><h2 id="overview-setup-heading">{translate('overview.setup')}</h2></div>
      <p>{translate('overview.setupOrganizations')}</p>
      <Link className="primary-button compact-button" to="/organizations">{translate('overview.addOrganization')}</Link>
    </section>}
    <HomeReminders workspace={null} client={operationsClient} primaryAction={organizationCount !== null && organizationCount > 0} />
  </>
}
