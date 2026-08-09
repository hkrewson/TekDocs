import type { Crepe } from '@milkdown/crepe'
import type { ToolbarFeatureConfig } from '@milkdown/crepe/feature/toolbar'
import { commandsCtx, editorViewCtx, remarkStringifyOptionsCtx } from '@milkdown/kit/core'
import { markRule } from '@milkdown/kit/prose'
import { toggleMark } from '@milkdown/kit/prose/commands'
import { Plugin } from '@milkdown/kit/prose/state'
import { Decoration, DecorationSet } from '@milkdown/kit/prose/view'
import { isMarkSelectedCommand } from '@milkdown/kit/preset/commonmark'
import { $command, $inputRule, $markSchema, $prose, $remark } from '@milkdown/kit/utils'

type MarkdownNode = {
  type: string
  value?: string
  children?: MarkdownNode[]
}

type MarkdownHandlerState = {
  containerPhrasing(node: MarkdownNode, info: MarkdownHandlerInfo): string
  enter(name: string): () => void
}

type MarkdownHandlerInfo = {
  before: string
  after: string
  [key: string]: unknown
}

const highlightPattern = /(?<![\w=])==(?=\S)([^=\n]*?\S)==(?![\w=])/g
const calloutPattern = /^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]/

export const calloutTypes = ['NOTE', 'TIP', 'IMPORTANT', 'WARNING', 'CAUTION'] as const
export type CalloutType = (typeof calloutTypes)[number]

export function normalizeTekDocsMarkdown(markdown: string): string {
  return markdown.replace(
    /^(\s*>\s*)\\(\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\])/gm,
    '$1$2',
  )
}

function splitHighlights(node: MarkdownNode): void {
  if (!node.children || node.type === 'code' || node.type === 'inlineCode') return
  const nextChildren: MarkdownNode[] = []
  for (const child of node.children) {
    if (child.type !== 'text' || !child.value?.includes('==')) {
      splitHighlights(child)
      nextChildren.push(child)
      continue
    }
    let cursor = 0
    for (const match of child.value.matchAll(highlightPattern)) {
      const index = match.index
      if (index > cursor) nextChildren.push({ type: 'text', value: child.value.slice(cursor, index) })
      nextChildren.push({
        type: 'semanticHighlight',
        children: [{ type: 'text', value: match[1] }],
      })
      cursor = index + match[0].length
    }
    if (cursor < child.value.length) nextChildren.push({ type: 'text', value: child.value.slice(cursor) })
  }
  node.children = nextChildren
}

const semanticHighlightRemark = $remark('tekdocsSemanticHighlight', () => () => (tree: MarkdownNode) => {
  splitHighlights(tree)
})

export const semanticHighlightSchema = $markSchema('semantic_highlight', () => ({
  parseDOM: [{ tag: 'mark' }],
  toDOM: () => ['mark', { class: 'semantic-highlight' }, 0],
  parseMarkdown: {
    match: (node) => node.type === 'semanticHighlight',
    runner: (state, node, markType) => {
      state.openMark(markType)
      state.next(node.children)
      state.closeMark(markType)
    },
  },
  toMarkdown: {
    match: (mark) => mark.type.name === 'semantic_highlight',
    runner: (state, mark) => {
      state.withMark(mark, 'semanticHighlight')
    },
  },
}))

export const toggleSemanticHighlightCommand = $command('ToggleSemanticHighlight', (ctx) => () =>
  toggleMark(semanticHighlightSchema.type(ctx)),
)

const semanticHighlightInputRule = $inputRule((ctx) =>
  markRule(/(?<![\w=])(==)([^=\n]*?\S)==$/, semanticHighlightSchema.type(ctx)),
)

function serializeSemanticHighlight(
  node: MarkdownNode,
  _parent: MarkdownNode | undefined,
  state: MarkdownHandlerState,
  info: MarkdownHandlerInfo,
): string {
  const exit = state.enter('semanticHighlight')
  const content = state.containerPhrasing(node, { ...info, before: '==', after: '==' })
  exit()
  return `==${content}==`
}

const calloutDecorations = $prose(() => new Plugin({
  props: {
    decorations(state) {
      const decorations: Decoration[] = []
      state.doc.descendants((node, position) => {
        if (node.type.name !== 'blockquote') return
        const match = calloutPattern.exec(node.textContent)
        if (!match) return
        const type = match[1].toLowerCase()
        decorations.push(Decoration.node(position, position + node.nodeSize, {
          class: `callout callout-${type}`,
          'data-callout': type,
        }))
      })
      return DecorationSet.create(state.doc, decorations)
    },
  },
}))

const highlightIcon = '<svg viewBox="0 0 24 24"><path d="m9 11-6 6v3h9l3-3"/><path d="m22 12-7.5 7.5L4.5 9.5 12 2l10 10Z"/></svg>'
const clearIcon = '<svg viewBox="0 0 24 24"><path d="m7 21-4-4 10-10 4 4L7 21Z"/><path d="m14 6 3-3 4 4-3 3"/><path d="M5 19h16"/></svg>'

export function configureTekDocsMarkdown(instance: Crepe): void {
  instance.editor
    .config((ctx) => {
      ctx.update(remarkStringifyOptionsCtx, (options) => ({
        ...options,
        handlers: {
          ...options.handlers,
          semanticHighlight: serializeSemanticHighlight,
        },
      }))
    })
    .use(semanticHighlightRemark)
    .use(semanticHighlightSchema)
    .use(toggleSemanticHighlightCommand)
    .use(semanticHighlightInputRule)
    .use(calloutDecorations)
}

type ToolbarBuilder = Parameters<NonNullable<ToolbarFeatureConfig['buildToolbar']>>[0]

export function extendSelectionToolbar(builder: ToolbarBuilder): void {
  builder.getGroup('formatting').addItem('highlight', {
    icon: highlightIcon,
    label: 'Highlight',
    active: (ctx) => ctx.get(commandsCtx).call(
      isMarkSelectedCommand.key,
      semanticHighlightSchema.type(ctx),
    ),
    onRun: (ctx) => {
      ctx.get(commandsCtx).call(toggleSemanticHighlightCommand.key)
    },
  })
  builder.addGroup('cleanup', 'Cleanup').addItem('clear-formatting', {
    icon: clearIcon,
    label: 'Remove formatting',
    active: () => false,
    onRun: (ctx) => {
      const view = ctx.get(editorViewCtx)
      const { from, to } = view.state.selection
      if (from === to) return
      view.dispatch(view.state.tr.removeMark(from, to))
    },
  })
}
