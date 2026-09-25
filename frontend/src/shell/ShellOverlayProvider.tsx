import { useState } from 'react'
import type { ReactNode } from 'react'
import { ShellOverlayContext } from './overlayContext'

export function ShellOverlayProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<string | null>(null)
  return <ShellOverlayContext.Provider value={{ active, setActive }}>{children}</ShellOverlayContext.Provider>
}
