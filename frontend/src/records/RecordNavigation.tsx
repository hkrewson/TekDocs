import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { translate } from '../i18n/localization'

export function RecordHeader({ recordId, section, title, description }: {
  recordId: string; section: string; title: string; description?: ReactNode
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus({ preventScroll: true }) }, [recordId, section])
  return <header className="record-header"><h1 ref={heading} tabIndex={-1}>{title}</h1>{description && <p>{description}</p>}</header>
}

export type RecordSection = { id: string; label: string; href: string }

/** Callers supply only authorized sections and a valid current section. */
export function RecordSections({ sections, current }: { sections: readonly RecordSection[]; current: string }) {
  const navigate = useNavigate()
  const location = useLocation()
  return <>
    <nav className="record-sections" aria-label={translate('collections.sections')}>
      {sections.map((section) => <Link key={section.id} to={section.href} state={location.state as unknown} aria-current={current === section.id ? 'page' : undefined}>{section.label}</Link>)}
    </nav>
    <label className="record-sections-mobile">{translate('collections.sections')}<select aria-label={translate('collections.sections')} value={current} onChange={(event) => {
      const target = sections.find((section) => section.id === event.target.value)
      if (target) void navigate(target.href, { state: location.state as unknown })
    }}>{sections.map((section) => <option key={section.id} value={section.id}>{section.label}</option>)}</select></label>
  </>
}
