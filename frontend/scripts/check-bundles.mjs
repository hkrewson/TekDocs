import { readdir, readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { gzipSync } from 'node:zlib'

// Budgets are measured on the compressed payload, because that is what crosses the
// wire. A raw-byte ceiling penalises what this codebase does well: design tokens and
// repeated declarations cost real uncompressed bytes and almost nothing gzipped, so a
// raw budget pressures refactors no user can perceive. Raw sizes are still reported
// on failure for context. Default gzip settings approximate an ordinary server rather
// than a best case, so the measurement stays conservative.
const assetDirectory = resolve(process.argv[2] ?? 'dist', 'assets')
const shellBudget = 128 * 1024
const lazyDependencyBudget = 176 * 1024
const editorBudget = 400 * 1024
const pdfViewerBudget = 144 * 1024
const mermaidBudget = 36 * 1024
const shellStyleBudget = 24 * 1024
const editorStyleBudget = 20 * 1024
const assets = await readdir(assetDirectory)
const measure = async (name) => {
  const contents = await readFile(resolve(assetDirectory, name))
  return { name, size: gzipSync(contents).byteLength, raw: contents.byteLength }
}
const javascript = await Promise.all(assets.filter((name) => name.endsWith('.js')).map(measure))
const editor = javascript.find(({ name }) => name.startsWith('EditorSpike-'))
const shell = javascript.find(({ name }) => name.startsWith('index-'))
const pdfViewer = javascript.find(({ name }) => name.startsWith('PdfViewer-'))
const mermaidDiagram = javascript.find(({ name }) => name.startsWith('MermaidDiagram-'))
if (!editor) {
  process.stderr.write('The editor must remain a separately loaded route chunk.\n')
  process.exit(1)
}
if (!shell) {
  process.stderr.write('The application shell chunk was not found.\n')
  process.exit(1)
}
if (!pdfViewer) {
  process.stderr.write('PDF.js must remain a separately loaded document-viewer chunk.\n')
  process.exit(1)
}
if (!mermaidDiagram) {
  process.stderr.write('Mermaid must remain a separately loaded diagram chunk.\n')
  process.exit(1)
}
const oversized = javascript.filter(({ name, size }) => {
  const budget = name === editor.name
    ? editorBudget
    : name === pdfViewer.name
      ? pdfViewerBudget
      : name === mermaidDiagram.name
        ? mermaidBudget
        : name === shell.name
          ? shellBudget
          : lazyDependencyBudget
  return size > budget
})
if (oversized.length > 0) {
  for (const asset of oversized) {
    process.stderr.write(`${asset.name} exceeds its JavaScript budget at ${asset.size} compressed bytes (${asset.raw} raw).\n`)
  }
  process.exit(1)
}
const styles = await Promise.all(assets.filter((name) => name.endsWith('.css')).map(measure))
for (const style of styles) {
  const budget = style.name.startsWith('EditorSpike-') ? editorStyleBudget : shellStyleBudget
  if (style.size > budget) {
    process.stderr.write(`${style.name} exceeds its stylesheet budget at ${style.size} compressed bytes (${style.raw} raw).\n`)
    process.exit(1)
  }
}
const shellStyle = styles.find(({ name }) => name.startsWith('index-'))
process.stdout.write(`Frontend bundle budget passed (compressed bytes): shell=${shell.size}<=${shellBudget} lazy-dependency<=${lazyDependencyBudget} editor=${editor.size}<=${editorBudget} pdf=${pdfViewer.size}<=${pdfViewerBudget} mermaid=${mermaidDiagram.size}<=${mermaidBudget} shell-style=${shellStyle?.size ?? 0}<=${shellStyleBudget}\n`)
