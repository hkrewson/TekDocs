import { createContext, useContext, useCallback, useEffect, useId, useLayoutEffect, useRef } from 'react'

export type EditState = { dirty: boolean; busy: boolean; active: boolean; discard?: () => void }
export type NavigationGuard = {
  isGuarded: boolean
  register: (id: string, state: EditState | null) => void
  attempt: (action: () => void) => void
}
export const NavigationGuardContext = createContext<NavigationGuard | null>(null)

export function useNavigationGuard() {
  const context = useContext(NavigationGuardContext)
  if (!context) throw new Error('NavigationGuardProvider is required')
  return context.attempt
}

export function useUnsavedChanges(dirty: boolean, busy = false, onDiscard?: () => void, active = dirty) {
  const context = useContext(NavigationGuardContext)
  if (!context) throw new Error('NavigationGuardProvider is required')
  const { register, attempt } = context
  const id = useId()
  const discardRef = useRef(onDiscard)
  useLayoutEffect(() => { discardRef.current = onDiscard }, [onDiscard])
  const discard = useCallback(() => discardRef.current?.(), [])
  useEffect(() => {
    register(id, { dirty, busy, active, discard })
    return () => register(id, null)
  }, [id, dirty, busy, active, register, discard])
  return attempt
}
