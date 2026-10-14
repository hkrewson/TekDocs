import { useEffect, useRef, useState } from 'react'
import { useRouteError } from 'react-router'
import { translate } from '../i18n/localization'

export function ApplicationError() {
  const error: unknown = useRouteError()
  const message = error instanceof Error ? error.message : ''
  // Browser engines use different messages for a rejected dynamic import.
  // Do not classify ordinary API fetch failures or display raw error details.
  const moduleFailed = /Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Loading chunk [\w-]+ failed/i.test(message)
  const [acknowledged, setAcknowledged] = useState(false)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [])

  return <main className="content-section" aria-labelledby="application-error-heading">
    <h1 id="application-error-heading" ref={heading} tabIndex={-1}>
      {translate(moduleFailed ? 'applicationError.moduleTitle' : 'applicationError.title')}
    </h1>
    <p>{translate(moduleFailed ? 'applicationError.moduleHelp' : 'applicationError.help')}</p>
    <p>{translate('applicationError.unsavedWarning')}</p>
    <label className="checkbox-field">
      <input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} />
      {translate('applicationError.acknowledge')}
    </label>
    <button type="button" className="primary-button" disabled={!acknowledged} onClick={() => window.location.reload()}>
      {translate('applicationError.reload')}
    </button>
    <p>{translate('applicationError.persistentHelp')}</p>
  </main>
}
