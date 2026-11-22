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
  it('restores canonical wikilinks escaped by the visual editor serializer', () => {
    const id = '11111111-1111-4111-8111-111111111111'
    expect(normalizeTekDocsMarkdown(`See \\[\\[${id}|Runbook\\]\\].`))
      .toBe(`See [[${id}|Runbook]].`)
    expect(normalizeTekDocsMarkdown(`See \\[\\[${id}|Runbook]].`))
      .toBe(`See [[${id}|Runbook]].`)
  })

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

  it.each([
    ['document wikilink', '[[11111111-1111-4111-8111-111111111111|Runbook]]', '[[11111111-1111-4111-8111-111111111111|Runbook]]'],
    ['record reference', '[Router](tekdocs://entity/22222222-2222-4222-8222-222222222222)', '[Router](tekdocs://entity/22222222-2222-4222-8222-222222222222)'],
    ['reusable content key', '<tekdocs://key/steps.content>', '<tekdocs://key/steps.content>'],
    ['file reference', '[setup.txt](tekdocs://attachment/33333333-3333-4333-8333-333333333333)', '[setup.txt](tekdocs://attachment/33333333-3333-4333-8333-333333333333)'],
  ])('preserves an inserted %s', async (_name, source, expected) => {
    const root = document.createElement('div')
    document.body.append(root)
    const instance = new Crepe({
      root,
      defaultValue: '',
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
    instance.editor.action(ctx => {
      const view = ctx.get(editorViewCtx)
      view.dispatch(view.state.tr.insertText(source, view.state.selection.from))
    })
    expect(normalizeTekDocsMarkdown(instance.getMarkdown())).toContain(expected)

    await instance.destroy()
    root.remove()
  })
})
