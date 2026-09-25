import { useContext, useEffect } from 'react'
import { ShellOverlayContext } from './overlayContext'

export function useShellOverlay(id: string) {
  const context = useContext(ShellOverlayContext)
  const setActive = context?.setActive
  useEffect(() => () => setActive?.((current) => current === id ? null : current), [id, setActive])
  return {
    blocked: Boolean(context?.active && context.active !== id),
    activate: () => {
      if (context?.active && context.active !== id) return false
      setActive?.(id)
      return true
    },
    release: () => setActive?.((current) => current === id ? null : current),
  }
}
