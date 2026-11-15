import { NavLink } from 'react-router'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'

export function DataModelNavigation({ workspace }: { workspace: WorkspaceContext | null }) {
  const fieldsPath = workspace ? `/workspaces/organizations/${encodeURIComponent(workspace.id)}/custom_fields` : '/custom-fields'
  return <nav className="local-view-navigation" aria-label={translate('dataModel.navigation')}>
    <NavLink to={fieldsPath}>{translate('dataModel.fields')}</NavLink>
    {!workspace && <NavLink to="/taxonomies">{translate('dataModel.categories')}</NavLink>}
  </nav>
}
