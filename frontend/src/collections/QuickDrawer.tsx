import { useEffect, useId, useRef } from 'react'
import type { MouseEvent, ReactNode } from 'react'
import { translate } from '../i18n/localization'

export function QuickDrawer({ title, children, onClose, returnFocusId, returnHref }: { title: string; children: ReactNode; onClose: () => void; returnFocusId?: string; returnHref: string }) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const heading = useRef<HTMLHeadingElement>(null)
  const pressedOutside = useRef(false)
  useEffect(() => {
    const dialog = ref.current!
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog.showModal()
    heading.current?.focus({ preventScroll: true })
    return () => {
      dialog.close(); document.body.style.overflow = overflow
      if (previous?.isConnected && previous !== document.body) previous.focus({ preventScroll: true })
      else if (returnFocusId) document.getElementById(returnFocusId)?.focus({ preventScroll: true })
    }
  }, [returnFocusId])
  return <dialog ref={ref} className="collection-drawer" aria-labelledby={titleId} onPointerDown={(event) => { pressedOutside.current = event.button === 0 && isBackdrop(event) }} onPointerCancel={() => { pressedOutside.current = false }} onClick={(event) => {
    const dismiss = pressedOutside.current && isBackdrop(event)
    pressedOutside.current = false
    if (dismiss) onClose()
  }} onCancel={(event) => { event.preventDefault(); onClose() }} onKeyDown={(event) => {
    if (event.key !== 'Tab') return
    const controls = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), summary, a[href], input:not(:disabled), select:not(:disabled), [tabindex="0"]')].filter((element) => element.getClientRects().length > 0)
    const first = controls[0], last = controls.at(-1)
    if (event.shiftKey && (document.activeElement === first || document.activeElement === heading.current)) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }}>
    <header><h2 ref={heading} tabIndex={-1} id={titleId}>{title}</h2><a className="collection-drawer-return" href={returnHref} onClick={(event) => { event.preventDefault(); onClose() }}>{translate('collections.return')}</a></header>
    <div className="collection-drawer-body">{title.length > 80 && <details><summary>{translate('collections.fullName')}</summary><p>{title}</p></details>}{children}</div>
  </dialog>
}

function isBackdrop(event: MouseEvent<HTMLDialogElement>) {
  if (event.target !== event.currentTarget) return false
  const bounds = event.currentTarget.getBoundingClientRect()
  return event.clientX < bounds.left || event.clientX >= bounds.right || event.clientY < bounds.top || event.clientY >= bounds.bottom
}
