import { Crepe, CrepeFeature } from '@milkdown/crepe'
import '@milkdown/crepe/theme/common/style.css'
import '@milkdown/crepe/theme/frame.css'
import { commandsCtx, editorViewCtx } from '@milkdown/kit/core'
import { clearTextInCurrentBlockCommand } from '@milkdown/kit/preset/commonmark'
import { lazy, Suspense, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

import { translate } from '../i18n/localization'
import { EditorControls } from './EditorControls'
import { MarkdownHelp } from './MarkdownHelp'
import { SanitizedMarkdown } from './SanitizedMarkdown'
import { renderMarkdownPreview } from './api'
import { markdownFixture } from './fixtures'
import { configureTekDocsMarkdown, extendSelectionToolbar, normalizeTekDocsMarkdown } from './markdownExtensions'

const DiagramEditor = lazy(async () => ({ default: (await import('./DiagramEditor')).DiagramEditor }))

type EditorMode = 'wysiwyg' | 'markdown' | 'preview' | 'help'
type PreviewState = { phase: 'idle' | 'loading' } | { phase: 'ready'; html: string } | { phase: 'error'; message: string }
const editorModes: EditorMode[] = ['wysiwyg', 'markdown', 'preview', 'help']
export type EditorInsertCommand = 'document' | 'fragment' | 'record' | 'file'
export type EditorInsert = (markdown: string) => void

const commandIcon = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M6 3h9l3 3v15H6zM9 11h6M9 15h6"/></svg>'

export function EditorSpike({ initialMarkdown = markdownFixture, title = 'Firewall replacement', description = 'Canonical Markdown editor', organizationId, documentId, onMarkdownChange, onInsertCommand, disabled = false }: { initialMarkdown?: string; title?: string; description?: string; organizationId?: string; documentId?: string; onMarkdownChange?: (markdown: string) => void; onInsertCommand?: (command: EditorInsertCommand, insert: EditorInsert) => void; disabled?: boolean }) {
  const editorRoot = useRef<HTMLDivElement>(null)
  const diagramButton = useRef<HTMLButtonElement>(null)
  const [editor, setEditor] = useState<Crepe | null>(null)
  const [mode, setMode] = useState<EditorMode>('wysiwyg')
  const [markdown, setMarkdown] = useState(initialMarkdown)
  const markdownValue = useRef(initialMarkdown)
  const [editorSeed, setEditorSeed] = useState(initialMarkdown)
  const [preview, setPreview] = useState<PreviewState>({ phase: 'idle' })
  const [diagramOpen, setDiagramOpen] = useState(false)
  const markdownChange = useRef(onMarkdownChange)
  const insertCommand = useRef(onInsertCommand)
  const editorDisabled = useRef(disabled)
  const tabsId = useId()
  const tabRefs = useRef<Record<EditorMode, HTMLButtonElement | null>>({ wysiwyg: null, markdown: null, preview: null, help: null })
  const requestedTabFocus = useRef<EditorMode | null>(null)
  useEffect(() => { markdownChange.current = onMarkdownChange }, [onMarkdownChange])
  useEffect(() => { insertCommand.current = onInsertCommand }, [onInsertCommand])
  useEffect(() => {
    if (initialMarkdown === markdownValue.current) return
    markdownValue.current = initialMarkdown
    setMarkdown(initialMarkdown)
    setEditorSeed(initialMarkdown)
  }, [initialMarkdown])
  useEffect(() => {
    editorDisabled.current = disabled
    if (editor) editor.editor.action(ctx => ctx.get(editorViewCtx).setProps({ editable: () => !disabled }))
  }, [disabled, editor])

  useLayoutEffect(() => {
    if (requestedTabFocus.current !== mode) return
    tabRefs.current[mode]?.focus()
    requestedTabFocus.current = null
  }, [mode])

  useEffect(() => {
    if (mode !== 'wysiwyg' || !editorRoot.current) return
    let active = true
    const instance = new Crepe({
      root: editorRoot.current,
      defaultValue: editorSeed,
      features: {
        [CrepeFeature.CodeMirror]: false,
        [CrepeFeature.Cursor]: false,
        [CrepeFeature.ImageBlock]: false,
        [CrepeFeature.Latex]: false,
        [CrepeFeature.TopBar]: false,
      },
      featureConfigs: {
        [CrepeFeature.Toolbar]: { buildToolbar: extendSelectionToolbar },
        [CrepeFeature.BlockEdit]: {
          buildMenu: (builder) => {
            const group = builder.addGroup('tekdocs', translate('editor.commands.group'))
            const add = (command: EditorInsertCommand, label: string) => { group.addItem(command, {
              label,
              icon: commandIcon,
              onRun: (ctx) => {
                if (editorDisabled.current) return
                ctx.get(commandsCtx).call(clearTextInCurrentBlockCommand.key)
                insertCommand.current?.(command, (value) => {
                  const view = ctx.get(editorViewCtx)
                  const position = view.state.selection.from
                  view.dispatch(view.state.tr.insertText(value, position).scrollIntoView())
                  view.focus()
                })
              },
            }) }
            add('document', translate('editor.commands.document'))
            add('fragment', translate('editor.commands.fragment'))
            add('record', translate('editor.commands.record'))
            add('file', translate('editor.commands.file'))
          },
        },
      },
    })
    configureTekDocsMarkdown(instance)
    instance.on((listener) => {
      listener.markdownUpdated((_ctx, value) => {
        const normalized = normalizeTekDocsMarkdown(value)
        markdownValue.current = normalized
        setMarkdown(normalized)
        markdownChange.current?.(normalized)
      })
    })
    void instance.create().then(() => {
      if (!active) return
      instance.editor.action(ctx => {
        const view = ctx.get(editorViewCtx)
        view.dom.setAttribute('aria-label', translate('editor.markdownBody'))
        view.dom.setAttribute('aria-multiline', 'true')
      })
      setEditor(instance)
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
    markdownValue.current = markdown
    setEditorSeed(markdown)
    setMode('wysiwyg')
  }

  const leaveEditor = (nextMode: Exclude<EditorMode, 'wysiwyg'>) => {
    if (mode === 'wysiwyg' && editor) {
      const normalized = normalizeTekDocsMarkdown(editor.getMarkdown())
      markdownValue.current = normalized
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

  const openDiagrams = () => {
    const current = editor ? normalizeTekDocsMarkdown(editor.getMarkdown()) : markdown
    markdownValue.current = current
    setMarkdown(current)
    markdownChange.current?.(current)
    setDiagramOpen(true)
  }

  const saveDiagram = (value: string) => {
    markdownValue.current = value
    setMarkdown(value)
    setEditorSeed(value)
    markdownChange.current?.(value)
    setPreview({ phase: 'loading' })
    requestedTabFocus.current = 'preview'
    setMode('preview')
    setDiagramOpen(false)
  }

  const closeDiagram = () => {
    setDiagramOpen(false)
    requestAnimationFrame(() => diagramButton.current?.focus())
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
    requestedTabFocus.current = nextMode
    selectMode(nextMode)
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
        <div><strong>{title}</strong>{description && <span>{description}</span>}</div>
        <div className="mode-tabs" role="tablist" aria-label="Editor mode">
          {tab('wysiwyg', 'Editor')}
          {tab('markdown', 'Markdown')}
          {tab('preview', 'Preview')}
          {tab('help', 'Formatting help')}
        </div>
      </div>
      {mode === 'wysiwyg' && <div id={`${tabsId}-wysiwyg-panel`} role="tabpanel" aria-labelledby={`${tabsId}-wysiwyg-tab`}>
        <EditorControls editor={editor} ready={editor !== null && !disabled} onDiagram={openDiagrams} diagramButtonRef={diagramButton} />
        <div className="milkdown-host" ref={editorRoot} />
      </div>}
      {mode === 'markdown' && <div id={`${tabsId}-markdown-panel`} role="tabpanel" aria-labelledby={`${tabsId}-markdown-tab`}><textarea className="markdown-source" disabled={disabled} value={markdown} onChange={(event) => { markdownValue.current = event.target.value; setMarkdown(event.target.value); markdownChange.current?.(event.target.value) }} aria-label="Markdown source" spellCheck="false" /></div>}
      {mode === 'preview' && <div id={`${tabsId}-preview-panel`} role="tabpanel" aria-labelledby={`${tabsId}-preview-tab`}>
        {preview.phase === 'loading' && <div className="markdown-preview-state" role="status">Rendering secure preview…</div>}
        {preview.phase === 'error' && <div className="markdown-preview-state" role="alert">{preview.message}</div>}
        {preview.phase === 'ready' && <SanitizedMarkdown html={preview.html} />}
      </div>}
      {mode === 'help' && <div id={`${tabsId}-help-panel`} role="tabpanel" aria-labelledby={`${tabsId}-help-tab`}><MarkdownHelp /></div>}
      {diagramOpen && <Suspense fallback={<p role="status">Loading diagram editor…</p>}><DiagramEditor markdown={markdown} onSave={saveDiagram} onCancel={closeDiagram} /></Suspense>}
    </section>
  )
}
