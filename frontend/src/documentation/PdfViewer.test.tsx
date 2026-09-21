import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

const renderPage = vi.fn().mockReturnValue({ promise: Promise.resolve(), cancel: vi.fn() })
const destroy = vi.fn().mockResolvedValue(undefined)
const getPage = vi.fn().mockResolvedValue({
  getViewport: () => ({ width: 600, height: 800 }),
  render: renderPage,
  getTextContent: vi.fn().mockResolvedValue({ items: [{ str: 'Accessible setup guide' }] }),
})

vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: { workerSrc: '' },
  getDocument: () => ({ promise: Promise.resolve({ numPages: 2, getPage }), destroy }),
}))

import { PdfViewer } from './PdfViewer'

it('loads a protected PDF as bytes and exposes navigation, text, and download controls', async () => {
  const user = userEvent.setup()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, arrayBuffer: vi.fn().mockResolvedValue(new ArrayBuffer(8)) }))
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as CanvasRenderingContext2D)
  render(<PdfViewer filename="setup.pdf" url="/api/files/setup" onClose={vi.fn()} />)
  expect(await screen.findByText('Page 1 of 2')).toBeVisible()
  await waitFor(() => expect(renderPage).toHaveBeenCalled())
  await user.click(screen.getByRole('button', { name: 'Next' }))
  expect(await screen.findByText('Page 2 of 2')).toBeVisible()
  await user.click(screen.getByText('Page text'))
  expect(await screen.findByText('Accessible setup guide')).toBeVisible()
  await user.type(screen.getByRole('searchbox', { name: 'Search PDF' }), 'setup')
  await user.click(screen.getByRole('button', { name: 'Search' }))
  expect(await screen.findByText('Found on page 1.')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute('href', '/api/files/setup')
  expect(fetch).toHaveBeenCalledWith('/api/files/setup', expect.objectContaining({ credentials: 'same-origin' }))
})

it('fails closed on viewer disagreement while retaining download and keyboard close', async () => {
  const user = userEvent.setup()
  const onClose = vi.fn()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))
  render(<PdfViewer filename="unreadable.pdf" url="/api/files/unreadable" onClose={onClose} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('The PDF could not be opened.')
  expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute('href', '/api/files/unreadable')
  await user.keyboard('{Escape}')
  expect(onClose).toHaveBeenCalledOnce()
})

it('starts a different PDF on page one with fresh search state', async () => {
  const user = userEvent.setup()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, arrayBuffer: vi.fn().mockResolvedValue(new ArrayBuffer(8)) }))
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as CanvasRenderingContext2D)
  const { rerender } = render(<PdfViewer filename="first.pdf" url="/api/files/first" onClose={vi.fn()} />)
  await screen.findByText('Page 1 of 2')
  await user.click(screen.getByRole('button', { name: 'Next' }))
  await user.type(screen.getByRole('searchbox', { name: 'Search PDF' }), 'old query')
  rerender(<PdfViewer filename="second.pdf" url="/api/files/second" onClose={vi.fn()} />)
  expect(await screen.findByText('Page 1 of 2')).toBeVisible()
  expect(screen.getByRole('searchbox', { name: 'Search PDF' })).toHaveValue('')
})

it('retries a failed load without exposing parser or request details', async () => {
  const user = userEvent.setup()
  vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new Error('Internal parser detail')).mockResolvedValue({ ok: true, arrayBuffer: vi.fn().mockResolvedValue(new ArrayBuffer(8)) }))
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as CanvasRenderingContext2D)
  render(<PdfViewer filename="retry.pdf" url="/api/files/retry" onClose={vi.fn()} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('The PDF could not be opened.')
  expect(screen.queryByText('Internal parser detail')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('Page 1 of 2')).toBeVisible()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('cancels an unfinished canvas render before zooming', async () => {
  const user = userEvent.setup()
  let rejectRender!: (error: Error) => void
  const cancel = vi.fn(() => rejectRender(new Error('Rendering cancelled')))
  renderPage.mockReturnValueOnce({ promise: new Promise<void>((_resolve, reject) => { rejectRender = reject }), cancel })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, arrayBuffer: vi.fn().mockResolvedValue(new ArrayBuffer(8)) }))
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as CanvasRenderingContext2D)
  render(<PdfViewer filename="zoom.pdf" url="/api/files/zoom" onClose={vi.fn()} />)
  await screen.findByText('Page 1 of 2')
  await waitFor(() => expect(renderPage).toHaveBeenCalled())
  await user.click(screen.getByRole('button', { name: 'Zoom in' }))
  expect(cancel).toHaveBeenCalledOnce()
  expect(screen.getByText('140%')).toBeVisible()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('keeps search focus on parent updates and uses the latest close callback', async () => {
  const user = userEvent.setup()
  const originalClose = vi.fn(), latestClose = vi.fn()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, arrayBuffer: vi.fn().mockResolvedValue(new ArrayBuffer(8)) }))
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as CanvasRenderingContext2D)
  const { rerender } = render(<PdfViewer filename="focus.pdf" url="/api/files/focus" onClose={originalClose} />)
  await screen.findByText('Page 1 of 2')
  await user.click(screen.getByRole('searchbox', { name: 'Search PDF' }))
  rerender(<PdfViewer filename="focus.pdf" url="/api/files/focus" onClose={latestClose} />)
  expect(screen.getByRole('searchbox', { name: 'Search PDF' })).toHaveFocus()
  await user.keyboard('{Escape}')
  expect(latestClose).toHaveBeenCalledOnce()
  expect(originalClose).not.toHaveBeenCalled()
})
