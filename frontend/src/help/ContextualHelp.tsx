import { useEffect, useRef, useState } from 'react'
import { CircleHelp, ExternalLink, X } from 'lucide-react'
import { translate } from '../i18n/localization'
import { trapOverlayFocus } from '../shell/focusTrap'
import { useShellOverlay } from '../shell/useShellOverlay'
import { helpTopicForPath, helpTopicUrl, WIKI_PUBLISHED } from './topics'

export function ContextualHelp({ pathname }: { pathname: string }) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const dialogRef = useRef<HTMLElement>(null)
  const overlay = useShellOverlay('context-help')
  const topic = helpTopicForPath(pathname)

  useEffect(() => {
    if (!open) return
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    headingRef.current?.focus()
    const closeOutside = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false)
        overlay.release()
        triggerRef.current?.focus()
      }
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        overlay.release()
        triggerRef.current?.focus()
      }
    }
    document.addEventListener('mousedown', closeOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = overflow
      document.removeEventListener('mousedown', closeOutside)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [open, overlay])

  function toggle() {
    if (open) {
      setOpen(false)
      overlay.release()
      return
    }
    if (overlay.activate()) setOpen(true)
  }

  return (
    <div className="context-help" ref={containerRef}>
      <button ref={triggerRef} type="button" className="context-help-trigger" aria-label={translate('help.openLabel', { title: topic.title })} aria-haspopup="dialog" aria-expanded={open} disabled={overlay.blocked} onClick={toggle}>
        <CircleHelp size={19} aria-hidden="true" />
        <span>{translate('help.help')}</span>
      </button>
      {open && <section ref={dialogRef} className="context-help-popover notification-popover" role="dialog" aria-modal="true" aria-label={translate('help.dialogLabel', { title: topic.title })} onKeyDown={(event) => trapOverlayFocus(event, dialogRef)}>
        <header><h2 ref={headingRef} id="context-help-heading" tabIndex={-1}>{topic.title}</h2><button type="button" className="icon-button notification-close" aria-label={translate('help.close')} onClick={() => { setOpen(false); overlay.release(); triggerRef.current?.focus() }}><X size={18} aria-hidden="true" /></button></header>
        <div className="notification-popover-body context-help-popover-body">
          <p>{topic.summary}</p>
          {WIKI_PUBLISHED
            ? <a href={helpTopicUrl(topic)} target="_blank" rel="noreferrer">{translate('help.openGuide')} <ExternalLink size={14} aria-hidden="true" /></a>
            : <p className="context-help-status" role="status">{translate('help.unpublished')}</p>}
        </div>
      </section>}
    </div>
  )
}
