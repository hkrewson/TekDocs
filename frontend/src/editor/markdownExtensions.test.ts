import { Crepe, CrepeFeature } from '@milkdown/crepe'
import { commandsCtx, editorViewCtx } from '@milkdown/kit/core'
import { TextSelection } from '@milkdown/kit/prose/state'

import { markdownRoundTripFixture } from './fixtures'
import {
  configureTekDocsMarkdown,
  normalizeTekDocsMarkdown,
  toggleSemanticHighlightCommand,
} from './markdownExtensions'

describe('TekDocs Milkdown dialect', () => {
  it('semantically round-trips highlight and the supported technical blocks', async () => {
    const root = document.createElement('div')
    document.body.append(root)
    const instance = new Crepe({
      root,
      defaultValue: markdownRoundTripFixture,
      features: {
        [CrepeFeature.BlockEdit]: false,
        [CrepeFeature.CodeMirror]: false,
        [CrepeFeature.Cursor]: false,
        [CrepeFeature.ImageBlock]: false,
        [CrepeFeature.Latex]: false,
        [CrepeFeature.LinkTooltip]: false,
        [CrepeFeature.ListItem]: false,
        [CrepeFeature.Placeholder]: false,
        [CrepeFeature.Table]: false,
        [CrepeFeature.Toolbar]: false,
        [CrepeFeature.TopBar]: false,
      },
    })
    configureTekDocsMarkdown(instance)

    await instance.create()
    const output = normalizeTekDocsMarkdown(instance.getMarkdown())

    expect(root.querySelector('mark')).toHaveTextContent('semantic highlight')
    expect(output).toContain('# UniFi Network Setup Guide')
    expect(output).toContain('==semantic highlight==')
    expect(output).toContain('> [!WARNING]')
    expect(output).toMatch(/[*-] \[x] Export the current configuration/)
    expect(output).toContain('| Port')
    expect(output).toContain('[^exception]')

    instance.editor.action((ctx) => {
      const view = ctx.get(editorViewCtx)
      let from = -1
      view.state.doc.descendants((node, position) => {
        const offset = node.text?.indexOf('UniFi') ?? -1
        if (offset >= 0) from = position + offset
      })
      expect(from).toBeGreaterThan(0)
      view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, from, from + 5)))
      ctx.get(commandsCtx).call(toggleSemanticHighlightCommand.key)
    })
    expect(normalizeTekDocsMarkdown(instance.getMarkdown())).toContain('==UniFi==')

    await instance.destroy()
    root.remove()
  })
})
