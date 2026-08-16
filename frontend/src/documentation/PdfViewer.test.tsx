import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

const renderPage = vi.fn().mockReturnValue({ promise: Promise.resolve() })
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
  await user.click(screen.getByText('Accessible page text'))
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
  expect(await screen.findByRole('alert')).toHaveTextContent('The PDF could not be loaded.')
  expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute('href', '/api/files/unreadable')
  await user.keyboard('{Escape}')
  expect(onClose).toHaveBeenCalledOnce()
})
