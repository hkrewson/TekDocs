import type { Crepe } from '@milkdown/crepe'
import { commandsCtx, editorViewCtx } from '@milkdown/kit/core'
import { redoCommand, undoCommand } from '@milkdown/kit/plugin/history'
import {
  addBlockTypeCommand,
  blockquoteSchema,
  bulletListSchema,
  codeBlockSchema,
  headingSchema,
  hrSchema,
  listItemSchema,
  orderedListSchema,
  paragraphSchema,
  selectTextNearPosCommand,
  setBlockTypeCommand,
  wrapInBlockTypeCommand,
} from '@milkdown/kit/preset/commonmark'
import { createTable } from '@milkdown/kit/preset/gfm'
import {
  Code2,
  List,
  ListChecks,
  ListOrdered,
  Minus,
  Quote,
  Redo2,
  Table2,
  Undo2,
} from 'lucide-react'
import type { ChangeEvent, PointerEvent } from 'react'

import { calloutTypes, type CalloutType } from './markdownExtensions'

type Props = {
  editor: Crepe | null
  ready: boolean
}

function preserveSelection(event: PointerEvent<HTMLButtonElement>): void {
  event.preventDefault()
}

export function EditorControls({ editor, ready }: Props) {
  const act = (action: (instance: Crepe) => void) => {
    if (editor && ready) action(editor)
  }

  const setTextStyle = (event: ChangeEvent<HTMLSelectElement>) => {
    const value = event.target.value
    event.target.value = ''
    if (!value) return
    act((instance) => instance.editor.action((ctx) => {
      const commands = ctx.get(commandsCtx)
      if (value === 'paragraph') {
        commands.call(setBlockTypeCommand.key, { nodeType: paragraphSchema.type(ctx) })
      } else {
        commands.call(setBlockTypeCommand.key, {
          nodeType: headingSchema.type(ctx),
          attrs: { level: Number(value.slice(1)) },
        })
      }
    }))
  }

  const wrapList = (ordered: boolean) => act((instance) => instance.editor.action((ctx) => {
    ctx.get(commandsCtx).call(wrapInBlockTypeCommand.key, {
      nodeType: ordered ? orderedListSchema.type(ctx) : bulletListSchema.type(ctx),
    })
  }))

  const taskList = () => act((instance) => instance.editor.action((ctx) => {
    const commands = ctx.get(commandsCtx)
    commands.call(wrapInBlockTypeCommand.key, { nodeType: bulletListSchema.type(ctx) })
    const view = ctx.get(editorViewCtx)
    const { $from } = view.state.selection
    for (let depth = $from.depth; depth > 0; depth -= 1) {
      if ($from.node(depth).type !== listItemSchema.type(ctx)) continue
      const position = $from.before(depth)
      view.dispatch(view.state.tr.setNodeMarkup(position, undefined, {
        ...$from.node(depth).attrs,
        checked: false,
      }))
      break
    }
  }))

  const addCallout = (event: ChangeEvent<HTMLSelectElement>) => {
    const type = event.target.value as CalloutType | ''
    event.target.value = ''
    if (!type) return
    act((instance) => instance.editor.action((ctx) => {
      let view = ctx.get(editorViewCtx)
      const inBlockquote = Array.from({ length: view.state.selection.$from.depth + 1 }, (_, depth) => depth)
        .some((depth) => view.state.selection.$from.node(depth).type === blockquoteSchema.type(ctx))
      if (!inBlockquote) {
        ctx.get(commandsCtx).call(wrapInBlockTypeCommand.key, { nodeType: blockquoteSchema.type(ctx) })
        view = ctx.get(editorViewCtx)
      }
      const start = view.state.selection.$from.start()
      if (!calloutTypes.some((candidate) => view.state.selection.$from.parent.textContent.startsWith(`[!${candidate}]`))) {
        view.dispatch(view.state.tr.insertText(`[!${type}]\n`, start))
      }
      view.focus()
    }))
  }

  const button = (
    label: string,
    icon: React.ReactNode,
    action: (instance: Crepe) => void,
  ) => (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={!ready}
      onPointerDown={preserveSelection}
      onClick={() => act(action)}
    >
      {icon}
    </button>
  )

  return (
    <div className="editor-format-controls" role="toolbar" aria-label="Block formatting">
      <select aria-label="Text style" defaultValue="" disabled={!ready} onChange={setTextStyle}>
        <option value="" disabled>Text style</option>
        <option value="paragraph">Paragraph</option>
        <option value="h1">Heading 1</option>
        <option value="h2">Heading 2</option>
        <option value="h3">Heading 3</option>
        <option value="h4">Heading 4</option>
      </select>
      <span className="editor-control-group" aria-label="Lists">
        {button('Bulleted list', <List size={17} />, () => wrapList(false))}
        {button('Numbered list', <ListOrdered size={17} />, () => wrapList(true))}
        {button('Task list', <ListChecks size={17} />, taskList)}
      </span>
      <span className="editor-control-group" aria-label="Blocks">
        {button('Blockquote', <Quote size={17} />, (instance) => instance.editor.action((ctx) => {
          ctx.get(commandsCtx).call(wrapInBlockTypeCommand.key, { nodeType: blockquoteSchema.type(ctx) })
        }))}
        {button('Code block', <Code2 size={17} />, (instance) => instance.editor.action((ctx) => {
          ctx.get(commandsCtx).call(setBlockTypeCommand.key, { nodeType: codeBlockSchema.type(ctx) })
        }))}
        {button('Insert table', <Table2 size={17} />, (instance) => instance.editor.action((ctx) => {
          const commands = ctx.get(commandsCtx)
          const position = ctx.get(editorViewCtx).state.selection.from
          commands.call(addBlockTypeCommand.key, { nodeType: createTable(ctx, 3, 3) })
          commands.call(selectTextNearPosCommand.key, { pos: position })
        }))}
        {button('Insert divider', <Minus size={17} />, (instance) => instance.editor.action((ctx) => {
          ctx.get(commandsCtx).call(addBlockTypeCommand.key, { nodeType: hrSchema.type(ctx) })
        }))}
      </span>
      <select aria-label="Insert callout" defaultValue="" disabled={!ready} onChange={addCallout}>
        <option value="" disabled>Callout</option>
        {calloutTypes.map((type) => <option value={type} key={type}>{type.charAt(0) + type.slice(1).toLowerCase()}</option>)}
      </select>
      <span className="editor-control-group editor-history-controls" aria-label="History">
        {button('Undo', <Undo2 size={17} />, (instance) => instance.editor.action((ctx) => {
          ctx.get(commandsCtx).call(undoCommand.key)
        }))}
        {button('Redo', <Redo2 size={17} />, (instance) => instance.editor.action((ctx) => {
          ctx.get(commandsCtx).call(redoCommand.key)
        }))}
      </span>
    </div>
  )
}
