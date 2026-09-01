import { useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Filter, X } from 'lucide-react'
import { translate } from './i18n/localization'

export type FilterChoice = { value: string; label: string }

export type FilterMenuGroup = {
  kind: 'choices'
  label: string
  value: string
  choices: FilterChoice[]
  onChange: (value: string) => void
} | {
  kind: 'custom'
  label: string
  valueLabel: string
  content: ReactNode
}

export function FilterMenu({ groups, activeCount, onClear, label = translate('filters.label'), menuLabel = translate('filters.label') }: {
  groups: FilterMenuGroup[]
  activeCount: number
  onClear: () => void
  label?: string
  menuLabel?: string
}) {
  const [open, setOpen] = useState(false)
  const id = `filter-menu-${useId().replaceAll(':', '')}`
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    menuRef.current?.querySelector<HTMLElement>('summary')?.focus()
    const closeOnPointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node) && !triggerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      setOpen(false)
      triggerRef.current?.focus()
    }
    document.addEventListener('pointerdown', closeOnPointerDown)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOnPointerDown)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [open])

  const close = () => {
    setOpen(false)
    triggerRef.current?.focus()
  }

  return <div className="filter-control">
    <button ref={triggerRef} className="secondary-button filter-trigger" type="button" aria-haspopup="dialog" aria-controls={id} aria-expanded={open} onClick={() => setOpen((current) => !current)}>
      <Filter size={16} aria-hidden="true" />
      <span>{label}{activeCount > 0 ? ` (${activeCount})` : ''}</span>
    </button>
    {open && <div ref={menuRef} id={id} className="filter-menu" role="dialog" aria-label={menuLabel}>
      <div className="filter-menu-heading"><strong>{label}</strong><button className="icon-button" type="button" aria-label={translate('filters.close')} onClick={close}><X size={16} /></button></div>
      {groups.map((group) => {
        const valueLabel = group.kind === 'choices' ? group.choices.find((choice) => choice.value === group.value)?.label ?? group.choices[0]?.label ?? '' : group.valueLabel
        return <details key={group.label} className="filter-menu-group">
          <summary><span>{group.label}</span><span>{valueLabel}</span></summary>
          {group.kind === 'choices'
            ? <div className="filter-menu-choices" role="radiogroup" aria-label={group.label}>{group.choices.map((choice) => <label key={choice.value || 'all'}><input type="radio" name={`${id}-${group.label}`} value={choice.value} checked={group.value === choice.value} onChange={() => group.onChange(choice.value)} /><span>{choice.label}</span></label>)}</div>
            : group.content}
        </details>
      })}
      <div className="filter-menu-footer"><button type="button" disabled={activeCount === 0} onClick={onClear}>{translate('filters.clear')}</button></div>
    </div>}
  </div>
}
