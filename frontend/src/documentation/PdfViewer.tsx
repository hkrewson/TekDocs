import { useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, Download, Minus, Plus, X } from 'lucide-react'
import { translate } from '../i18n/localization'
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist'
import type { PDFDocumentLoadingTask, PDFDocumentProxy } from 'pdfjs-dist'

GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

export function PdfViewer({ filename, url, onClose }: { filename: string; url: string; onClose: () => void }) {
  const viewerRef = useRef<HTMLElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null)
  const [page, setPage] = useState(1)
  const [scale, setScale] = useState(1.2)
  const [text, setText] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchStatus, setSearchStatus] = useState('')
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    viewerRef.current?.focus()
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  useEffect(() => {
    const controller = new AbortController()
    let loadingTask: PDFDocumentLoadingTask | null = null
    fetch(url, { credentials: 'same-origin', signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(translate('pdf.loadFailed'))
        return response.arrayBuffer()
      })
      .then(async (data) => {
        loadingTask = getDocument({ data })
        const loaded = await loadingTask.promise
        if (!controller.signal.aborted) setDocument(loaded)
      })
      .catch((loadError: unknown) => {
        if (!controller.signal.aborted) setError(loadError instanceof Error ? loadError.message : translate('pdf.loadFailed'))
      })
    return () => {
      controller.abort()
      void loadingTask?.destroy()
    }
  }, [url])

  useEffect(() => {
    if (!document || !canvasRef.current) return
    let cancelled = false
    const render = async () => {
      const pdfPage = await document.getPage(page)
      const viewport = pdfPage.getViewport({ scale })
      const canvas = canvasRef.current
      if (!canvas || cancelled) return
      const context = canvas.getContext('2d')
      if (!context) return
      canvas.width = Math.ceil(viewport.width)
      canvas.height = Math.ceil(viewport.height)
      await pdfPage.render({ canvas, canvasContext: context, viewport }).promise
      const content = await pdfPage.getTextContent()
      if (!cancelled) setText(content.items.map((item) => 'str' in item ? item.str : '').join(' '))
    }
    void render().catch(() => { if (!cancelled) setError(translate('pdf.renderFailed')) })
    return () => { cancelled = true }
  }, [document, page, scale])

  const search = async () => {
    const query = searchQuery.trim().toLocaleLowerCase()
    if (!document || !query) {
      setSearchStatus(query ? translate('pdf.stillLoading') : translate('pdf.enterSearch'))
      return
    }
    setSearching(true)
    setSearchStatus(translate('pdf.searching'))
    try {
      for (let candidate = 1; candidate <= document.numPages; candidate += 1) {
        const pdfPage = await document.getPage(candidate)
        const content = await pdfPage.getTextContent()
        const pageText = content.items.map((item) => 'str' in item ? item.str : '').join(' ').toLocaleLowerCase()
        if (pageText.includes(query)) {
          setPage(candidate)
          setSearchStatus(translate('pdf.foundOnPage', { page: candidate }))
          return
        }
      }
      setSearchStatus(translate('pdf.noMatches'))
    } catch {
      setSearchStatus(translate('pdf.searchFailed'))
    } finally {
      setSearching(false)
    }
  }

  return <section ref={viewerRef} className="pdf-viewer" aria-labelledby="pdf-viewer-heading" tabIndex={-1}>
    <header><div><h3 id="pdf-viewer-heading">{filename}</h3><p>{document ? translate('pdf.pageCount', { page, count: document.numPages }) : translate('pdf.loading')}</p></div><button className="icon-button" type="button" aria-label={translate('pdf.close')} onClick={onClose}><X size={17} /></button></header>
    {error && <div><p className="form-message error" role="alert">{error}</p><p>{translate('pdf.downloadRecovery')}</p><a className="secondary-button" href={url}><Download size={15} />{translate('files.download')}</a></div>}
    {!error && <><nav aria-label={translate('pdf.controls')}><button className="secondary-button" type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={15} />{translate('common.previous')}</button><button className="secondary-button" type="button" disabled={!document || page >= document.numPages} onClick={() => setPage((value) => value + 1)}>{translate('common.next')}<ChevronRight size={15} /></button><button className="icon-button" type="button" aria-label={translate('pdf.zoomOut')} disabled={scale <= .6} onClick={() => setScale((value) => Math.max(.6, value - .2))}><Minus size={16} /></button><span aria-live="polite">{Math.round(scale * 100)}%</span><button className="icon-button" type="button" aria-label={translate('pdf.zoomIn')} disabled={scale >= 2.4} onClick={() => setScale((value) => Math.min(2.4, value + .2))}><Plus size={16} /></button><form role="search" onSubmit={(event) => { event.preventDefault(); void search() }}><label className="sr-only" htmlFor="pdf-search">{translate('pdf.search')}</label><input id="pdf-search" type="search" value={searchQuery} maxLength={120} placeholder={translate('pdf.search')} onChange={(event) => setSearchQuery(event.target.value)} /><button className="secondary-button" type="submit" disabled={searching || !document}>{translate('documentation.search')}</button></form><a className="secondary-button" href={url}><Download size={15} />{translate('files.download')}</a></nav><p role="status">{searchStatus}</p><div className="pdf-canvas"><canvas ref={canvasRef} role="img" aria-label={translate('pdf.canvasLabel', { filename, page })} /></div><details><summary>{translate('pdf.accessibleText')}</summary><p>{text || translate('pdf.noText')}</p></details></>}
  </section>
}
