import { useLocation, useNavigate } from 'react-router'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'

export function DataModelNavigation({ workspace }: { workspace: WorkspaceContext | null }) {
  const location = useLocation()
  const navigate = useNavigate()
  const fieldsPath = workspace ? `/workspaces/organizations/${encodeURIComponent(workspace.id)}/custom_fields` : '/custom-fields'
  if (workspace) return null
  return <label className="collection-view-picker"><span>{translate('dataModel.view')}</span><select aria-label={translate('dataModel.view')} value={location.pathname === '/taxonomies' ? 'categories' : 'fields'} onChange={(event) => { void navigate(event.target.value === 'categories' ? '/taxonomies' : fieldsPath) }}><option value="fields">{translate('dataModel.fields')}</option><option value="categories">{translate('dataModel.categories')}</option></select></label>
}
