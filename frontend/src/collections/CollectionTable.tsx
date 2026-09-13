import type { ReactNode, SetStateAction } from 'react'
import { translate } from '../i18n/localization'

export function CollectionTable<T extends { id: string; name: string }>({ label, rows, columns, ordering, onOrder, selectable, selected, onSelection }: {
  label: string; rows: readonly T[]
  columns: Array<{ id: string; label: string; render: (row: T) => ReactNode }>
  ordering?: string; onOrder: (column: string) => void
  selectable: boolean; selected: ReadonlySet<string>; onSelection: (next: SetStateAction<Set<string>>) => void
}) {
  return <table className="collection-table" aria-label={label}>
    <thead><tr>
      {selectable && <th className="collection-selection"><input type="checkbox" aria-label={translate('collections.selectPage')} checked={rows.length > 0 && rows.every((row) => selected.has(row.id))} onChange={(event) => onSelection(new Set(event.target.checked ? rows.map((row) => row.id) : []))} /></th>}
      {columns.map((column) => <th key={column.id} className={column.id === 'name' ? 'collection-identity' : ''} scope="col" aria-sort={ordering === column.id ? 'ascending' : ordering === `-${column.id}` ? 'descending' : 'none'}><button type="button" onClick={() => onOrder(ordering === column.id ? `-${column.id}` : column.id)}>{column.label}{ordering === column.id ? ' ↑' : ordering === `-${column.id}` ? ' ↓' : ''}</button></th>)}
    </tr></thead>
    <tbody>{rows.map((row) => <tr key={row.id}>
      {selectable && <td className="collection-selection"><input type="checkbox" aria-label={translate('collections.select', { name: row.name })} checked={selected.has(row.id)} onChange={(event) => { const checked = event.target.checked; onSelection((current) => { const next = new Set(current); if (checked) next.add(row.id); else next.delete(row.id); return next }) }} /></td>}
      {columns.map((column) => <td key={column.id} data-column={column.id} className={column.id === 'name' ? 'collection-identity' : ''}>{column.id !== 'name' && <span className="collection-cell-label">{column.label}</span>}{column.render(row)}</td>)}
    </tr>)}</tbody>
  </table>
}
