import { readdir, stat } from 'node:fs/promises'
import { resolve } from 'node:path'

const assetDirectory = resolve(process.argv[2] ?? 'dist', 'assets')
const shellBudget = 500 * 1024
const editorBudget = 1200 * 1024
const assets = await readdir(assetDirectory)
const javascript = await Promise.all(
  assets.filter((name) => name.endsWith('.js')).map(async (name) => ({ name, size: (await stat(resolve(assetDirectory, name))).size })),
)
const editor = javascript.find(({ name }) => name.startsWith('EditorSpike-'))
if (!editor) {
  process.stderr.write('The editor must remain a separately loaded route chunk.\n')
  process.exit(1)
}
const oversized = javascript.filter(({ name, size }) => size > (name === editor.name ? editorBudget : shellBudget))
if (oversized.length > 0) {
  for (const asset of oversized) process.stderr.write(`${asset.name} exceeds its JavaScript budget at ${asset.size} bytes.\n`)
  process.exit(1)
}
process.stdout.write(`Frontend bundle budget passed: shell<=${shellBudget} editor=${editor.size}<=${editorBudget}\n`)
