import { useEffect, useRef, useState } from 'react'
import { BookOpenText, CircleHelp, ExternalLink } from 'lucide-react'
import { helpTopicForPath, helpTopicUrl, WIKI_PUBLISHED } from './topics'

export function ContextualHelp({ pathname }: { pathname: string }) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const topic = helpTopicForPath(pathname)

  useEffect(() => {
    if (!open) return
    const closeOutside = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    document.addEventListener('mousedown', closeOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('mousedown', closeOutside)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [open])

  return (
    <div className="context-help" ref={containerRef}>
      <button ref={triggerRef} type="button" className="context-help-trigger" aria-label={`Help for ${topic.title}`} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <CircleHelp size={19} aria-hidden="true" />
        <span>Help</span>
      </button>
      {open && <section className="context-help-popover" role="dialog" aria-label={`${topic.title} help`}>
        <header><BookOpenText size={18} aria-hidden="true" /><h2>{topic.title}</h2></header>
        <p>{topic.summary}</p>
        {WIKI_PUBLISHED
          ? <a href={helpTopicUrl(topic)} target="_blank" rel="noreferrer">Open the full guide <ExternalLink size={14} aria-hidden="true" /></a>
          : <p className="context-help-status" role="status">The public Wiki guide has not been published yet.</p>}
      </section>}
    </div>
  )
}
