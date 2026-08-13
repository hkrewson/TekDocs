import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const denied = /AGPL-1|SSPL|BUSL|Commons Clause|proprietary/i
const seen = new Set()
const failures = []

function inspectModules(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue
    if (entry.name.startsWith('.')) continue
    const path = join(directory, entry.name)
    if (entry.name.startsWith('@')) {
      inspectModules(path)
      continue
    }
    const manifestPath = join(path, 'package.json')
    let manifest
    try {
      manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
    } catch {
      failures.push(`${entry.name}: missing readable package manifest`)
      continue
    }
    const identity = `${manifest.name}@${manifest.version}`
    if (!seen.has(identity)) {
      seen.add(identity)
      const license = typeof manifest.license === 'string' ? manifest.license : ''
      if (!license) failures.push(`${identity}: missing license declaration`)
      else if (denied.test(license)) failures.push(`${identity}: prohibited license declaration`)
    }
    const nested = join(path, 'node_modules')
    try { inspectModules(nested) } catch (error) {
      if (error?.code !== 'ENOENT') throw error
    }
  }
}

inspectModules(new URL('../node_modules', import.meta.url).pathname)
if (failures.length) throw new Error([...new Set(failures)].sort().join('\n'))
console.log(`Frontend dependency license policy passed for ${seen.size} package versions.`)
