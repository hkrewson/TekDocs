import type { KeyboardEvent as ReactKeyboardEvent, RefObject } from 'react'

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export function trapOverlayFocus(event: ReactKeyboardEvent, container: RefObject<HTMLElement | null>) {
  if (event.key !== 'Tab') return
  const focusable = [...(container.current?.querySelectorAll<HTMLElement>(focusableSelector) ?? [])]
    .filter((element) => {
      const style = window.getComputedStyle(element)
      return !element.hidden && element.getAttribute('aria-hidden') !== 'true' && style.display !== 'none' && style.visibility !== 'hidden'
    })
  const first = focusable[0]
  const last = focusable.at(-1)
  if (!first || !last) {
    event.preventDefault()
    return
  }
  if (event.shiftKey && (document.activeElement === first || !container.current?.contains(document.activeElement))) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}
