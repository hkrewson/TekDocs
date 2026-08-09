import { Crepe, CrepeFeature } from '@milkdown/crepe'
import { useEffect, useRef, useState } from 'react'

import { EditorControls } from './EditorControls'
import { MarkdownHelp } from './MarkdownHelp'
import { SanitizedMarkdown } from './SanitizedMarkdown'
import { renderMarkdownPreview } from './api'
import { markdownFixture } from './fixtures'
import { configureTekDocsMarkdown, extendSelectionToolbar, normalizeTekDocsMarkdown } from './markdownExtensions'

type EditorMode = 'wysiwyg' | 'markdown' | 'preview' | 'help'
type PreviewState = { phase: 'idle' | 'loading' } | { phase: 'ready'; html: string } | { phase: 'error'; message: string }

export function EditorSpike({ initialMarkdown = markdownFixture, title = 'Firewall replacement', description = 'Canonical Markdown editor', onMarkdownChange }: { initialMarkdown?: string; title?: string; description?: string; onMarkdownChange?: (markdown: string) => void }) {
  const editorRoot = useRef<HTMLDivElement>(null)
  const [editor, setEditor] = useState<Crepe | null>(null)
  const [mode, setMode] = useState<EditorMode>('wysiwyg')
  const [markdown, setMarkdown] = useState(initialMarkdown)
  const [editorSeed, setEditorSeed] = useState(initialMarkdown)
  const [preview, setPreview] = useState<PreviewState>({ phase: 'idle' })
  const markdownChange = useRef(onMarkdownChange)
  useEffect(() => { markdownChange.current = onMarkdownChange }, [onMarkdownChange])

  useEffect(() => {
    if (mode !== 'wysiwyg' || !editorRoot.current) return
    let active = true
    const instance = new Crepe({
      root: editorRoot.current,
      defaultValue: editorSeed,
      features: {
        [CrepeFeature.ImageBlock]: false,
        [CrepeFeature.Latex]: false,
        [CrepeFeature.TopBar]: false,
      },
      featureConfigs: {
        [CrepeFeature.Toolbar]: { buildToolbar: extendSelectionToolbar },
      },
    })
    configureTekDocsMarkdown(instance)
    instance.on((listener) => {
      listener.markdownUpdated((_ctx, value) => {
        const normalized = normalizeTekDocsMarkdown(value)
        setMarkdown(normalized)
        markdownChange.current?.(normalized)
      })
    })
    void instance.create().then(() => {
      if (active) setEditor(instance)
    })
    return () => {
      active = false
      setEditor(null)
      void instance.destroy()
    }
  }, [editorSeed, mode])

  useEffect(() => {
    if (mode !== 'preview') return
    const controller = new AbortController()
    void renderMarkdownPreview(markdown, controller.signal)
      .then((html) => setPreview({ phase: 'ready', html }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setPreview({ phase: 'error', message: error instanceof Error ? error.message : 'The secure preview could not be loaded.' })
        }
      })
    return () => controller.abort()
  }, [markdown, mode])

  const showEditor = () => {
    setEditorSeed(markdown)
    setMode('wysiwyg')
  }

  const leaveEditor = (nextMode: Exclude<EditorMode, 'wysiwyg'>) => {
    if (editor) {
      const normalized = normalizeTekDocsMarkdown(editor.getMarkdown())
      setMarkdown(normalized)
      markdownChange.current?.(normalized)
    }
    if (nextMode === 'preview') setPreview({ phase: 'loading' })
    setMode(nextMode)
  }

  return (
    <section className="editor-section" aria-label="Markdown editor feasibility spike">
      <div className="editor-toolbar">
        <div>
          <strong>{title}</strong>
          <span>{description}</span>
        </div>
        <div className="mode-tabs" role="tablist" aria-label="Editor mode">
          <button className={mode === 'wysiwyg' ? 'selected' : ''} onClick={showEditor} role="tab" aria-selected={mode === 'wysiwyg'}>Editor</button>
          <button className={mode === 'markdown' ? 'selected' : ''} onClick={() => leaveEditor('markdown')} role="tab" aria-selected={mode === 'markdown'}>Markdown</button>
          <button className={mode === 'preview' ? 'selected' : ''} onClick={() => leaveEditor('preview')} role="tab" aria-selected={mode === 'preview'}>Preview</button>
          <button className={mode === 'help' ? 'selected' : ''} onClick={() => leaveEditor('help')} role="tab" aria-selected={mode === 'help'}>Formatting help</button>
        </div>
      </div>
      {mode === 'wysiwyg' && <>
        <EditorControls editor={editor} ready={editor !== null} />
        <div className="milkdown-host" ref={editorRoot} />
      </>}
      {mode === 'markdown' && <textarea className="markdown-source" value={markdown} onChange={(event) => { setMarkdown(event.target.value); markdownChange.current?.(event.target.value) }} aria-label="Markdown source" spellCheck="false" />}
      {mode === 'preview' && preview.phase === 'loading' && <div className="markdown-preview-state" role="status">Rendering secure preview…</div>}
      {mode === 'preview' && preview.phase === 'error' && <div className="markdown-preview-state" role="alert">{preview.message}</div>}
      {mode === 'preview' && preview.phase === 'ready' && <SanitizedMarkdown html={preview.html} />}
      {mode === 'help' && <MarkdownHelp />}
    </section>
  )
}
