import { useRef } from 'react'
import type { ReactNode } from 'react'
import { Ellipsis } from 'lucide-react'
import { translate } from '../i18n/localization'

export function RecordActionMenu({ children }: { children: ReactNode }) {
  const menu = useRef<HTMLDetailsElement>(null)
  return <details ref={menu} className="record-action-menu">
    <summary className="secondary-button"><Ellipsis size={16} aria-hidden="true" />{translate('common.more')}</summary>
    <div onClick={() => { if (menu.current) menu.current.open = false }}>{children}</div>
  </details>
}
