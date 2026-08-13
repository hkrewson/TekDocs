import { formatInteger, translate } from './i18n/localization'

type CollectionPaginationProps = {
  label: string
  page: number
  pageSize: number
  count: number
  hasMore: boolean
  onPageChange: (page: number) => void
}

export function CollectionPagination({ label, page, pageSize, count, hasMore, onPageChange }: CollectionPaginationProps) {
  if (count <= pageSize && page === 1) return null
  const first = count === 0 ? 0 : (page - 1) * pageSize + 1
  const last = Math.min(page * pageSize, count)
  return <nav className="collection-pagination" aria-label={translate('pagination.label', { label })}>
    <span aria-live="polite">{translate('pagination.range', { first: formatInteger(first), last: formatInteger(last), count: formatInteger(count) })}</span>
    <div>
      <button type="button" className="row-action" disabled={page === 1} onClick={() => onPageChange(page - 1)}>{translate('pagination.previous')}</button>
      <span>{translate('pagination.page', { page: formatInteger(page) })}</span>
      <button type="button" className="row-action" disabled={!hasMore} onClick={() => onPageChange(page + 1)}>{translate('pagination.next')}</button>
    </div>
  </nav>
}
