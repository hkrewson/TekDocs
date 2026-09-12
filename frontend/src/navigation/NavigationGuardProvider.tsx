import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useBlocker } from 'react-router'
import type { Blocker } from 'react-router'
import { NavigationGuardContext } from './navigationGuard'
import type { EditState } from './navigationGuard'

const UnsavedChangesDialog = lazy(() => import('./UnsavedChangesDialog'))

export function NavigationGuardProvider({ children }: { children: ReactNode }) {
  const [editors, setEditors] = useState<Record<string, EditState>>({})
  const [pending, setPending] = useState<null | (() => void)>(null)
  const [dismissedBlocker, setDismissedBlocker] = useState<Blocker | null>(null)
  const dirty = Object.values(editors).some((editor) => editor.dirty || editor.busy)
  const busy = Object.values(editors).some((editor) => editor.busy)
  const blocker = useBlocker(dirty)
  const register = useCallback((id: string, state: EditState | null) => {
    setEditors((current) => {
      if (state) return { ...current, [id]: state }
      const next = { ...current }
      delete next[id]
      return next
    })
  }, [])
  const attempt = useCallback((action: () => void) => {
    if (dirty) setPending((current) => current ?? action)
    else {
      for (const editor of Object.values(editors)) if (editor.active) editor.discard?.()
      action()
    }
  }, [dirty, editors])
  const value = useMemo(() => ({ register, attempt }), [register, attempt])

  useEffect(() => {
    if (!dirty) return
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [dirty])

  function keepEditing() {
    setPending(null)
    if (blocker.state === 'blocked') {
      // Router reset is a transition. Dismiss urgently so delayed focus restoration
      // cannot steal focus from the next field the technician starts editing.
      setDismissedBlocker(blocker)
      blocker.reset()
    }
  }
  function discard() {
    if (busy) return
    for (const editor of Object.values(editors)) if (editor.active) editor.discard?.()
    const action = pending
    setPending(null)
    if (blocker.state === 'blocked') { setDismissedBlocker(blocker); blocker.proceed() }
    else action?.()
  }

  return <NavigationGuardContext.Provider value={value}>
    {children}
    {(pending || (blocker.state === 'blocked' && blocker !== dismissedBlocker)) && <Suspense fallback={null}>
      <UnsavedChangesDialog dirty={dirty} busy={busy} onKeep={keepEditing} onDiscard={discard} />
    </Suspense>}
  </NavigationGuardContext.Provider>
}
