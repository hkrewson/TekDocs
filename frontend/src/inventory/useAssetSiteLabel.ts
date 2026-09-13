import { useEffect, useState } from 'react'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import { browserAssetSiteChoices } from './api'

export function useAssetSiteLabel(workspace: WorkspaceContext, value: string) {
  const key = `${workspace.id}:${value}`
  const [label, setLabel] = useState<{ key: string; name: string } | null>(null)
  useEffect(() => {
    if (!value) return
    const controller = new AbortController()
    browserAssetSiteChoices(workspace, '', 1, value, controller.signal).then((result) => {
      if (!controller.signal.aborted) setLabel({ key, name: result.selected?.name ?? translate('collections.siteUnavailable') })
    }).catch(() => { /* Keep the URL condition removable even when its label cannot load. */ })
    return () => controller.abort()
  }, [workspace, value, key])
  return value ? label?.key === key ? label.name : translate('collections.selectedSite') : translate('collections.all')
}
