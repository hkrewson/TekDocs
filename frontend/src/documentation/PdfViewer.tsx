import { useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, Download, Minus, Plus, X } from 'lucide-react'
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
        if (!response.ok) throw new Error('The PDF could not be loaded.')
        return response.arrayBuffer()
      })
      .then(async (data) => {
        loadingTask = getDocument({ data })
        const loaded = await loadingTask.promise
        if (!controller.signal.aborted) setDocument(loaded)
      })
      .catch((loadError: unknown) => {
        if (!controller.signal.aborted) setError(loadError instanceof Error ? loadError.message : 'The PDF could not be loaded.')
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
    void render().catch(() => { if (!cancelled) setError('This PDF page could not be rendered.') })
    return () => { cancelled = true }
  }, [document, page, scale])

  const search = async () => {
    const query = searchQuery.trim().toLocaleLowerCase()
    if (!document || !query) {
      setSearchStatus(query ? 'The PDF is still loading.' : 'Enter text to search this PDF.')
      return
    }
    setSearching(true)
    setSearchStatus('Searching…')
    try {
      for (let candidate = 1; candidate <= document.numPages; candidate += 1) {
        const pdfPage = await document.getPage(candidate)
        const content = await pdfPage.getTextContent()
        const pageText = content.items.map((item) => 'str' in item ? item.str : '').join(' ').toLocaleLowerCase()
        if (pageText.includes(query)) {
          setPage(candidate)
          setSearchStatus(`Found on page ${candidate}.`)
          return
        }
      }
      setSearchStatus('No matches found.')
    } catch {
      setSearchStatus('This PDF could not be searched.')
    } finally {
      setSearching(false)
    }
  }

  return <section ref={viewerRef} className="pdf-viewer" aria-labelledby="pdf-viewer-heading" tabIndex={-1}>
    <header><div><h3 id="pdf-viewer-heading">{filename}</h3><p>{document ? `Page ${page} of ${document.numPages}` : 'Loading PDF…'}</p></div><button className="icon-button" type="button" aria-label="Close PDF viewer" onClick={onClose}><X size={17} /></button></header>
    {error && <div><p className="form-message error" role="alert">{error}</p><p>The original file remains available for download.</p><a className="secondary-button" href={url}><Download size={15} />Download</a></div>}
    {!error && <><nav aria-label="PDF viewer controls"><button className="secondary-button" type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={15} />Previous</button><button className="secondary-button" type="button" disabled={!document || page >= document.numPages} onClick={() => setPage((value) => value + 1)}>Next<ChevronRight size={15} /></button><button className="icon-button" type="button" aria-label="Zoom out" disabled={scale <= .6} onClick={() => setScale((value) => Math.max(.6, value - .2))}><Minus size={16} /></button><span aria-live="polite">{Math.round(scale * 100)}%</span><button className="icon-button" type="button" aria-label="Zoom in" disabled={scale >= 2.4} onClick={() => setScale((value) => Math.min(2.4, value + .2))}><Plus size={16} /></button><form role="search" onSubmit={(event) => { event.preventDefault(); void search() }}><label className="sr-only" htmlFor="pdf-search">Search PDF</label><input id="pdf-search" type="search" value={searchQuery} maxLength={120} placeholder="Search PDF" onChange={(event) => setSearchQuery(event.target.value)} /><button className="secondary-button" type="submit" disabled={searching || !document}>Search</button></form><a className="secondary-button" href={url}><Download size={15} />Download</a></nav><p role="status">{searchStatus}</p><div className="pdf-canvas"><canvas ref={canvasRef} role="img" aria-label={`${filename}, page ${page}`} /></div><details><summary>Accessible page text</summary><p>{text || 'No extractable text is available for this page.'}</p></details></>}
  </section>
}
