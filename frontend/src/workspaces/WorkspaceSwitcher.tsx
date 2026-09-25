import { useEffect, useRef, useState } from 'react'
import { Building2, Check, ChevronDown, CornerLeftUp, Search } from 'lucide-react'
import { useNavigate } from 'react-router'
import { translate } from '../i18n/localization'
import { trapOverlayFocus } from '../shell/focusTrap'
import { useShellOverlay } from '../shell/useShellOverlay'
import type { WorkspaceClient, WorkspaceContext, WorkspaceOption } from './api'
import { classificationSummary, mspWorkspacePath, organizationWorkspacePath } from './navigation'
import type { WorkspaceArea } from './navigation'

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join('') || 'TD'
}

export function WorkspaceSwitcher({
  tenant,
  activeWorkspace,
  activeArea,
  client,
  collapsed,
  workspaceLoading,
  onNavigate,
}: {
  tenant: { id: string; name: string }
  activeWorkspace: WorkspaceContext | null
  activeArea: WorkspaceArea
  client: WorkspaceClient
  collapsed: boolean
  workspaceLoading: boolean
  onNavigate: () => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<WorkspaceOption[]>([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [phase, setPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const firstOptionRef = useRef<HTMLButtonElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const requestRef = useRef(0)
  const overlay = useShellOverlay('workspace-switcher')
  const navigate = useNavigate()
  const workspaceName = activeWorkspace?.name ?? tenant.name
  const workspaceLabel = activeWorkspace ? translate('workspaceSwitcher.classifiedWorkspace', { classification: classificationSummary(activeWorkspace.classifications) }) : translate('workspaceSwitcher.mspWorkspace')
  const searchClassification = activeWorkspace?.classifications.includes('client') ? 'client' : undefined
  const searchLabel = searchClassification ? translate('workspaceSwitcher.findClient') : translate('workspaceSwitcher.findOrganization')

  useEffect(() => {
    if (!open) return
    searchRef.current?.focus()
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false)
        overlay.release()
      }
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open, overlay])

  useEffect(() => {
    if (!open) return
    const requestId = ++requestRef.current
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.searchOrganizations(query, 1, controller.signal, searchClassification)
        .then((response) => {
          if (requestRef.current !== requestId) return
          setResults(response.results)
          setPage(response.page)
          setHasMore(response.has_more)
          setPhase('ready')
        })
        .catch(() => {
          if (controller.signal.aborted || requestRef.current !== requestId) return
          setPhase('error')
        })
    }, 180)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [client, open, query, searchClassification])

  async function loadMore() {
    const nextPage = page + 1
    const requestId = ++requestRef.current
    setLoadingMore(true)
    try {
      const response = await client.searchOrganizations(query, nextPage, undefined, searchClassification)
      if (requestRef.current !== requestId) return
      setResults((current) => [...current, ...response.results])
      setPage(response.page)
      setHasMore(response.has_more)
    } catch {
      if (requestRef.current === requestId) setPhase('error')
    } finally {
      if (requestRef.current === requestId) setLoadingMore(false)
    }
  }

  function closeAndRestoreFocus() {
    setOpen(false)
    overlay.release()
    window.setTimeout(() => triggerRef.current?.focus(), 0)
  }

  function beginSearch() {
    setResults([])
    setPage(1)
    setHasMore(false)
    setPhase('loading')
  }

  function selectMsp() {
    setOpen(false)
    overlay.release()
    onNavigate()
    void navigate(mspWorkspacePath(activeArea))
  }

  function selectOrganization(workspace: WorkspaceOption) {
    setOpen(false)
    overlay.release()
    onNavigate()
    void navigate(organizationWorkspacePath(workspace, activeArea))
  }

  return (
    <div className="workspace-switcher" ref={rootRef} onKeyDown={(event) => { if (event.key === 'Escape') closeAndRestoreFocus() }}>
      <button
        ref={triggerRef}
        className="tenant-switcher"
        type="button"
        title={collapsed ? workspaceName : undefined}
        aria-label={translate('workspaceSwitcher.triggerLabel', { name: workspaceName, type: workspaceLabel })}
        aria-expanded={open}
        aria-haspopup="dialog"
        disabled={workspaceLoading || overlay.blocked}
        onClick={() => {
          if (open) { closeAndRestoreFocus(); return }
          if (!overlay.activate()) return
          beginSearch()
          setOpen(true)
        }}
      >
        <span className="tenant-initials">{initials(workspaceName)}</span>
        {!collapsed && <><span className="tenant-copy"><strong>{workspaceLoading ? translate('workspaceSwitcher.loadingWorkspace') : workspaceName}</strong><span>{workspaceLabel}</span></span><ChevronDown size={15} /></>}
      </button>
      {open && (
        <div ref={dialogRef} className="workspace-switcher-popover" role="dialog" aria-label={translate('workspaceSwitcher.dialogLabel')} onKeyDown={(event) => trapOverlayFocus(event, dialogRef)}>
          <label className="workspace-switcher-search">
            <Search size={15} aria-hidden="true" />
            <span className="sr-only">{searchLabel}</span>
            <input
              ref={searchRef}
              value={query}
              onChange={(event) => { setQuery(event.target.value); beginSearch() }}
              onKeyDown={(event) => { if (event.key === 'ArrowDown') { event.preventDefault(); firstOptionRef.current?.focus() } }}
              placeholder={searchLabel}
              autoComplete="off"
            />
          </label>
          <div className="workspace-options" aria-live="polite">
            <button ref={firstOptionRef} type="button" className="workspace-option" onClick={selectMsp} aria-label={activeWorkspace ? translate('workspaceSwitcher.backToMspLabel', { name: tenant.name }) : translate('workspaceSwitcher.mspLabel', { name: tenant.name })} aria-current={activeWorkspace ? undefined : 'true'}>
              {activeWorkspace ? <CornerLeftUp size={17} aria-hidden="true" /> : <Building2 size={17} aria-hidden="true" />}
              <span><strong>{activeWorkspace ? translate('workspaceSwitcher.backToMsp', { name: tenant.name }) : tenant.name}</strong><span>{translate('workspaceSwitcher.mspWorkspace')}</span></span>
              {!activeWorkspace && <Check size={15} aria-label={translate('workspaceSwitcher.current')} />}
            </button>
            <div className="workspace-option-divider" />
            {phase === 'loading' && <p className="workspace-switcher-state">{translate('workspaceSwitcher.searching')}</p>}
            {phase === 'error' && <p className="workspace-switcher-state" role="alert">{translate('workspaceSwitcher.loadFailed')}</p>}
            {phase === 'ready' && results.length === 0 && <p className="workspace-switcher-state">{searchClassification ? translate('workspaceSwitcher.noClients') : translate('workspaceSwitcher.noOrganizations')}</p>}
            {results.map((workspace) => (
              <button key={workspace.id} type="button" className="workspace-option" onClick={() => selectOrganization(workspace)} aria-label={`${workspace.name}. ${classificationSummary(workspace.classifications)}`} aria-current={workspace.id === activeWorkspace?.id ? 'true' : undefined}>
                <span className="workspace-option-initials" aria-hidden="true">{initials(workspace.name)}</span>
                <span><strong>{workspace.name}</strong><span>{classificationSummary(workspace.classifications)}</span></span>
                {workspace.id === activeWorkspace?.id && <Check size={15} aria-label={translate('workspaceSwitcher.current')} />}
              </button>
            ))}
            {phase === 'ready' && hasMore && <button type="button" className="workspace-more" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? translate('workspaceSwitcher.loadingMore') : translate('workspaceSwitcher.showMore')}</button>}
          </div>
        </div>
      )}
    </div>
  )
}
