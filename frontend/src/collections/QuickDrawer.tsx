import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import { translate } from '../i18n/localization'

export function QuickDrawer({ title, children, onClose, returnFocusId }: { title: string; children: ReactNode; onClose: () => void; returnFocusId?: string }) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  useEffect(() => {
    const dialog = ref.current!
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog.showModal()
    return () => {
      dialog.close(); document.body.style.overflow = overflow
      if (previous?.isConnected && previous !== document.body) previous.focus({ preventScroll: true })
      else if (returnFocusId) document.getElementById(returnFocusId)?.focus({ preventScroll: true })
    }
  }, [returnFocusId])
  return <dialog ref={ref} className="collection-drawer" aria-labelledby={titleId} onCancel={(event) => { event.preventDefault(); onClose() }} onKeyDown={(event) => {
    if (event.key !== 'Tab') return
    const controls = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), summary, a[href], input:not(:disabled), select:not(:disabled), [tabindex="0"]')].filter((element) => element.getClientRects().length > 0)
    const first = controls[0], last = controls.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }}>
    <header><h2 id={titleId}>{title}</h2><button type="button" autoFocus className="secondary-button" onClick={onClose}>{translate('common.close')}</button></header>
    <div className="collection-drawer-body">{title.length > 80 && <details><summary>{translate('collections.fullName')}</summary><p>{title}</p></details>}{children}</div>
  </dialog>
}
