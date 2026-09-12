import { useEffect, useRef } from 'react'
import { translate } from '../i18n/localization'
import './unsavedChanges.css'

export default function UnsavedChangesDialog({ dirty, busy, onKeep, onDiscard }: { dirty: boolean; busy: boolean; onKeep: () => void; onDiscard: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = dialogRef.current!
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog.showModal()
    return () => {
      dialog.close()
      document.body.style.overflow = overflow
      if (previous?.isConnected) previous.focus({ preventScroll: true })
    }
  }, [])
  return <dialog ref={dialogRef} className="unsaved-changes-dialog" aria-labelledby="unsaved-changes-title" aria-describedby="unsaved-changes-description" onKeyDown={(event) => {
    if (event.key !== 'Tab') return
    const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')]
    const first = buttons[0], last = buttons[buttons.length - 1]
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }} onCancel={(event) => { event.preventDefault(); onKeep() }}>
    <h2 id="unsaved-changes-title">{translate(dirty ? 'navigation.unsaved.title' : 'navigation.unsaved.ready')}</h2>
    <p id="unsaved-changes-description">{translate(busy ? 'navigation.unsaved.saving' : dirty ? 'navigation.unsaved.description' : 'navigation.unsaved.finished')}</p>
    <div className="form-actions">
      <button type="button" autoFocus className="primary-button" onClick={onKeep}>{translate('navigation.unsaved.keep')}</button>
      <button type="button" className="secondary-button" disabled={busy} onClick={onDiscard}>{translate(dirty ? 'navigation.unsaved.discard' : 'navigation.unsaved.continue')}</button>
    </div>
  </dialog>
}
