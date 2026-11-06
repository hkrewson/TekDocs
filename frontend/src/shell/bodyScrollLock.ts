const BODY_SCROLL_LOCK_CLASS = 'tekdocs-scroll-locked'
const activeLocks = new Set<symbol>()

export function lockBodyScroll() {
  const lock = Symbol('body-scroll-lock')
  activeLocks.add(lock)
  document.body.classList.add(BODY_SCROLL_LOCK_CLASS)

  return () => {
    if (!activeLocks.delete(lock) || activeLocks.size > 0) return
    document.body.classList.remove(BODY_SCROLL_LOCK_CLASS)
  }
}
