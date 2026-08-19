/**
 * Static detection of hardcoded button labels.
 *
 * `docs/LOCALIZATION.md` requires new shared controls to use the message catalog
 * and existing copy to migrate as each surface is hardened. That obligation was
 * unenforceable and unmeasurable, so literals accumulated after the catalog seam
 * shipped. These helpers back the two ratchets in `buttonLabels.test.ts`.
 *
 * A label is "hardcoded" when a `<button>` renders text that did not come from an
 * expression. Icons, expressions, and nested elements are ignored, so
 * `<button aria-label={translate('x')}><Icon /><span>{translate('x')}</span></button>`
 * is clean while `<button><Icon />Save</button>` is not.
 *
 * The opening tag cannot be matched with `<button[^>]*>`: an arrow function in a
 * handler contains `>`, which ends the match early and leaks attribute source into
 * the label. Tag scanning therefore tracks brace depth and quoting.
 */

type Scan = { readonly end: number; readonly selfClosing: boolean }

/** Index just past the `>` that closes the tag starting at `start`. */
function endOfOpeningTag(source: string, start: number): Scan | null {
  let depth = 0
  let quote: string | null = null
  for (let index = start; index < source.length; index += 1) {
    const character = source[index]
    if (quote) {
      if (character === quote && source[index - 1] !== '\\') quote = null
      continue
    }
    if (character === '"' || character === "'" || character === '`') {
      quote = character
      continue
    }
    if (character === '{') depth += 1
    else if (character === '}') depth -= 1
    else if (character === '>' && depth === 0) return { end: index + 1, selfClosing: source[index - 1] === '/' }
  }
  return null
}

/** Remove `{...}` expressions, honouring nesting and ignoring braces inside strings. */
function stripExpressions(source: string): string {
  let output = ''
  let depth = 0
  let quote: string | null = null
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index]
    if (depth > 0) {
      if (quote) {
        if (character === quote && source[index - 1] !== '\\') quote = null
      } else if (character === '"' || character === "'" || character === '`') quote = character
      else if (character === '{') depth += 1
      else if (character === '}') depth -= 1
      continue
    }
    if (character === '{') {
      depth = 1
      continue
    }
    output += character
  }
  return output
}

/** Literal text rendered by each `<button>` element in a source file. */
export function hardcodedButtonLabels(source: string): string[] {
  const labels: string[] = []
  const opening = /<button(?=[\s>])/g
  for (const match of source.matchAll(opening)) {
    const tag = endOfOpeningTag(source, match.index)
    // `<button ... />` renders no children. Without this the close search would run
    // on to an unrelated `</button>` and report that element's source as a label.
    if (!tag || tag.selfClosing) continue
    const close = source.indexOf('</button>', tag.end)
    if (close === -1) continue
    const text = stripExpressions(source.slice(tag.end, close))
      .replace(/<[^>]*>/g, '')
      .replace(/&[a-z]+;/gi, '')
      .replace(/\s+/g, ' ')
      .trim()
    if (/[A-Za-z]/.test(text)) labels.push(text)
  }
  return labels
}
