import { createContext } from 'react'
import type { Dispatch, SetStateAction } from 'react'

export type ShellOverlayContextValue = {
  active: string | null
  setActive: Dispatch<SetStateAction<string | null>>
}

export const ShellOverlayContext = createContext<ShellOverlayContextValue | null>(null)
