import { RecordActivity } from '../records/RecordActivity'
import { translate } from '../i18n/localization'
import type { OperationsClient } from '../operations/api'
import type { WorkspaceContext } from '../workspaces/api'

export function SoftwareHistory({ assetId, workspace, client }: { assetId: string; workspace: WorkspaceContext; client?: Pick<OperationsClient, 'activity'> }) {
  return <RecordActivity entityId={assetId} workspace={workspace} client={client} description={translate('collections.historySoftware')} emptyLabel={translate('collections.softwareHistoryEmpty')} deniedLabel={translate('collections.softwareHistoryDenied')} actionLabels={{ 'asset.software.updated': translate('collections.softwareUpdated'), 'asset.created_from_catalog': translate('collections.assetCreated') }} />
}
