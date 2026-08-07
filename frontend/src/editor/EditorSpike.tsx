import { Crepe } from '@milkdown/crepe'
import { useEffect, useRef, useState } from 'react'

import { markdownFixture } from './fixtures'

type EditorMode = 'wysiwyg' | 'markdown'

export function EditorSpike() {
  const editorRoot = useRef<HTMLDivElement>(null)
  const editor = useRef<Crepe | null>(null)
  const [mode, setMode] = useState<EditorMode>('wysiwyg')
  const [markdown, setMarkdown] = useState(markdownFixture)
  const [editorSeed, setEditorSeed] = useState(markdownFixture)

  useEffect(() => {
    if (mode !== 'wysiwyg' || !editorRoot.current) return
    const instance = new Crepe({ root: editorRoot.current, defaultValue: editorSeed })
    instance.on((listener) => {
      listener.markdownUpdated((_ctx, value) => setMarkdown(value))
    })
    void instance.create()
    editor.current = instance
    return () => {
      editor.current = null
      void instance.destroy()
    }
  }, [editorSeed, mode])

  const showEditor = () => {
    setEditorSeed(markdown)
    setMode('wysiwyg')
  }

  return (
    <section className="editor-section" aria-label="Markdown editor feasibility spike">
      <div className="editor-toolbar">
        <div>
          <strong>Firewall replacement</strong>
          <span>Executable editor spike — content is not saved</span>
        </div>
        <div className="mode-tabs" role="tablist" aria-label="Editor mode">
          <button className={mode === 'wysiwyg' ? 'selected' : ''} onClick={showEditor} role="tab" aria-selected={mode === 'wysiwyg'}>Editor</button>
          <button className={mode === 'markdown' ? 'selected' : ''} onClick={() => setMode('markdown')} role="tab" aria-selected={mode === 'markdown'}>Markdown</button>
        </div>
      </div>
      {mode === 'wysiwyg' ? <div className="milkdown-host" ref={editorRoot} /> : (
        <textarea className="markdown-source" value={markdown} onChange={(event) => setMarkdown(event.target.value)} aria-label="Markdown source" spellCheck="false" />
      )}
    </section>
  )
}
