import { Crepe, CrepeFeature } from '@milkdown/crepe'
import '@milkdown/crepe/theme/common/style.css'
import '@milkdown/crepe/theme/frame.css'
import { useEffect, useId, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

import { EditorControls } from './EditorControls'
import { MarkdownHelp } from './MarkdownHelp'
import { SanitizedMarkdown } from './SanitizedMarkdown'
import { renderMarkdownPreview } from './api'
import { markdownFixture } from './fixtures'
import { configureTekDocsMarkdown, extendSelectionToolbar, normalizeTekDocsMarkdown } from './markdownExtensions'

type EditorMode = 'wysiwyg' | 'markdown' | 'preview' | 'help'
type PreviewState = { phase: 'idle' | 'loading' } | { phase: 'ready'; html: string } | { phase: 'error'; message: string }
const editorModes: EditorMode[] = ['wysiwyg', 'markdown', 'preview', 'help']

export function EditorSpike({ initialMarkdown = markdownFixture, title = 'Firewall replacement', description = 'Canonical Markdown editor', organizationId, documentId, onMarkdownChange }: { initialMarkdown?: string; title?: string; description?: string; organizationId?: string; documentId?: string; onMarkdownChange?: (markdown: string) => void }) {
  const editorRoot = useRef<HTMLDivElement>(null)
  const [editor, setEditor] = useState<Crepe | null>(null)
  const [mode, setMode] = useState<EditorMode>('wysiwyg')
  const [markdown, setMarkdown] = useState(initialMarkdown)
  const [editorSeed, setEditorSeed] = useState(initialMarkdown)
  const [preview, setPreview] = useState<PreviewState>({ phase: 'idle' })
  const markdownChange = useRef(onMarkdownChange)
  const tabsId = useId()
  const tabRefs = useRef<Record<EditorMode, HTMLButtonElement | null>>({ wysiwyg: null, markdown: null, preview: null, help: null })
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
    void renderMarkdownPreview(markdown, organizationId, documentId, controller.signal)
      .then((html) => setPreview({ phase: 'ready', html }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setPreview({ phase: 'error', message: error instanceof Error ? error.message : 'The secure preview could not be loaded.' })
        }
      })
    return () => controller.abort()
  }, [documentId, markdown, mode, organizationId])

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

  const selectMode = (nextMode: EditorMode) => {
    if (nextMode === 'wysiwyg') showEditor()
    else leaveEditor(nextMode)
  }

  const moveTab = (event: KeyboardEvent<HTMLButtonElement>, currentMode: EditorMode) => {
    const currentIndex = editorModes.indexOf(currentMode)
    let nextIndex: number | null = null
    if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % editorModes.length
    if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + editorModes.length) % editorModes.length
    if (event.key === 'Home') nextIndex = 0
    if (event.key === 'End') nextIndex = editorModes.length - 1
    if (nextIndex === null) return
    event.preventDefault()
    const nextMode = editorModes[nextIndex]
    selectMode(nextMode)
    requestAnimationFrame(() => tabRefs.current[nextMode]?.focus())
  }

  const tab = (tabMode: EditorMode, label: string) => (
    <button
      ref={(node) => { tabRefs.current[tabMode] = node }}
      id={`${tabsId}-${tabMode}-tab`}
      className={mode === tabMode ? 'selected' : ''}
      onClick={() => selectMode(tabMode)}
      onKeyDown={(event) => moveTab(event, tabMode)}
      role="tab"
      tabIndex={mode === tabMode ? 0 : -1}
      aria-selected={mode === tabMode}
      aria-controls={`${tabsId}-${tabMode}-panel`}
    >{label}</button>
  )

  return (
    <section className="editor-section" aria-label="Markdown editor feasibility spike">
      <div className="editor-toolbar">
        <div>
          <strong>{title}</strong>
          <span>{description}</span>
        </div>
        <div className="mode-tabs" role="tablist" aria-label="Editor mode">
          {tab('wysiwyg', 'Editor')}
          {tab('markdown', 'Markdown')}
          {tab('preview', 'Preview')}
          {tab('help', 'Formatting help')}
        </div>
      </div>
      {mode === 'wysiwyg' && <div id={`${tabsId}-wysiwyg-panel`} role="tabpanel" aria-labelledby={`${tabsId}-wysiwyg-tab`}>
        <EditorControls editor={editor} ready={editor !== null} />
        <div className="milkdown-host" ref={editorRoot} />
      </div>}
      {mode === 'markdown' && <div id={`${tabsId}-markdown-panel`} role="tabpanel" aria-labelledby={`${tabsId}-markdown-tab`}><textarea className="markdown-source" value={markdown} onChange={(event) => { setMarkdown(event.target.value); markdownChange.current?.(event.target.value) }} aria-label="Markdown source" spellCheck="false" /></div>}
      {mode === 'preview' && <div id={`${tabsId}-preview-panel`} role="tabpanel" aria-labelledby={`${tabsId}-preview-tab`}>
        {preview.phase === 'loading' && <div className="markdown-preview-state" role="status">Rendering secure preview…</div>}
        {preview.phase === 'error' && <div className="markdown-preview-state" role="alert">{preview.message}</div>}
        {preview.phase === 'ready' && <SanitizedMarkdown html={preview.html} />}
      </div>}
      {mode === 'help' && <div id={`${tabsId}-help-panel`} role="tabpanel" aria-labelledby={`${tabsId}-help-tab`}><MarkdownHelp /></div>}
    </section>
  )
}
