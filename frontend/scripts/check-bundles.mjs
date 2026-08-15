import { readdir, stat } from 'node:fs/promises'
import { resolve } from 'node:path'

const assetDirectory = resolve(process.argv[2] ?? 'dist', 'assets')
const shellBudget = 400 * 1024
const lazyDependencyBudget = 700 * 1024
const editorBudget = 1200 * 1024
const pdfViewerBudget = 500 * 1024
const mermaidBudget = 100 * 1024
const shellStyleBudget = 120 * 1024
const editorStyleBudget = 100 * 1024
const assets = await readdir(assetDirectory)
const javascript = await Promise.all(
  assets.filter((name) => name.endsWith('.js')).map(async (name) => ({ name, size: (await stat(resolve(assetDirectory, name))).size })),
)
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
  for (const asset of oversized) process.stderr.write(`${asset.name} exceeds its JavaScript budget at ${asset.size} bytes.\n`)
  process.exit(1)
}
const styles = await Promise.all(
  assets.filter((name) => name.endsWith('.css')).map(async (name) => ({ name, size: (await stat(resolve(assetDirectory, name))).size })),
)
for (const style of styles) {
  const budget = style.name.startsWith('EditorSpike-') ? editorStyleBudget : shellStyleBudget
  if (style.size > budget) {
    process.stderr.write(`${style.name} exceeds its stylesheet budget at ${style.size} bytes.\n`)
    process.exit(1)
  }
}
process.stdout.write(`Frontend bundle budget passed: shell=${shell.size}<=${shellBudget} lazy-dependency<=${lazyDependencyBudget} editor=${editor.size}<=${editorBudget} pdf=${pdfViewer.size}<=${pdfViewerBudget} mermaid=${mermaidDiagram.size}<=${mermaidBudget}\n`)
