import { readdir, readFile } from 'node:fs/promises'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = fileURLToPath(new URL('..', import.meta.url))
const sourceRoot = join(frontendRoot, 'src')
const domStyleAccess = /\.style\s*(?:\.|\[|=(?!=))/
const forbidden = [
  ['React style prop', /\bstyle\s*=\s*\{\s*\{/],
  ['DOM style access', domStyleAccess],
  ['DOM style attribute', /\bsetAttribute\s*\(\s*['"]style['"]/],
  ['CSS text mutation', /\.cssText\b|\binsertRule\s*\(/],
  ['raw HTML injection', /\bdangerouslySetInnerHTML\b/],
]

for (const [label, source, expected] of [
  ['domain equality', "item.style === 'wireless'", false],
  ['direct assignment', 'element.style = replacement', true],
  ['property mutation', "element.style.width = '10px'", true],
  ['indexed mutation', "element.style['width'] = '10px'", true],
]) {
  if (domStyleAccess.test(source) !== expected) throw new Error(`Invalid DOM style check: ${label}`)
}

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) files.push(...await sourceFiles(path))
    else if (/\.(?:ts|tsx)$/.test(entry.name) && !entry.name.includes('.test.')) files.push(path)
  }
  return files
}

const violations = []
for (const path of await sourceFiles(sourceRoot)) {
  const source = await readFile(path, 'utf8')
  for (const [label, pattern] of forbidden) {
    if (pattern.test(source)) violations.push(`${relative(frontendRoot, path)}: ${label}`)
  }
}

if (violations.length > 0) {
  process.stderr.write(`CSP source check failed:\n${violations.map((item) => `- ${item}`).join('\n')}\n`)
  process.exitCode = 1
} else {
  process.stdout.write('CSP source check passed: no application inline-style or raw-HTML sinks.\n')
}
