import { useState } from 'react'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import { translate } from '../i18n/localization'
import type { CollectionPreferences } from './preferences'

export function ColumnChooser({ preferences, labels, onSave, onReset }: {
  preferences: CollectionPreferences
  labels: Record<string, string>
  onSave: (columns: string[]) => Promise<void>
  onReset: () => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const attempt = useUnsavedChanges(open && JSON.stringify(draft) !== JSON.stringify(preferences.columns), busy, () => setOpen(false), open)
  async function save(reset: boolean) {
    setBusy(true); setError(false)
    try { if (reset) await onReset(); else await onSave(draft); setOpen(false) }
    catch { setError(true) }
    finally { setBusy(false) }
  }
  return <div className="collection-columns">
    <button className="secondary-button" type="button" aria-expanded={open} onClick={() => attempt(() => { setDraft([...preferences.columns]); setError(false); setOpen(!open) })}>{translate('collections.columns')}</button>
    {open && <form className="collection-column-choices" aria-label={translate('collections.columns')} onSubmit={(event) => { event.preventDefault(); void save(false) }}>
      <fieldset disabled={busy}><legend>{translate('collections.columns')}</legend>
        {preferences.available_columns.map((column) => <label key={column}><input type="checkbox" checked={draft.includes(column)} disabled={column === 'name'} onChange={(event) => setDraft(preferences.available_columns.filter((key) => key === column ? event.target.checked : draft.includes(key)))} />{labels[column] ?? column}</label>)}
      </fieldset>
      {error && <p role="alert">{translate('collections.preferenceFailed')}</p>}
      <div className="form-actions"><button className="primary-button" disabled={busy}>{translate('common.save')}</button><button className="secondary-button" type="button" disabled={busy} onClick={() => attempt(() => setOpen(false))}>{translate('common.cancel')}</button><button className="secondary-button" type="button" disabled={busy} onClick={() => { void save(true) }}>{translate('collections.reset')}</button></div>
    </form>}
  </div>
}
