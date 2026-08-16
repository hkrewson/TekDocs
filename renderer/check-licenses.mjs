import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const denied = /AGPL-1|SSPL|BUSL|Commons Clause|proprietary/i
const reviewedMissingDeclarations = new Map([
  ['khroma@2.1.0', { evidence: /The MIT License|Permission is hereby granted/ }],
])
const seen = new Set()
const failures = []

function inspectModules(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name.startsWith('.')) continue
    const modulePath = join(directory, entry.name)
    if (entry.name.startsWith('@')) {
      inspectModules(modulePath)
      continue
    }
    let manifest
    try {
      manifest = JSON.parse(readFileSync(join(modulePath, 'package.json'), 'utf8'))
    } catch {
      failures.push(`${entry.name}: missing readable package manifest`)
      continue
    }
    const identity = `${manifest.name}@${manifest.version}`
    if (!seen.has(identity)) {
      seen.add(identity)
      const license = typeof manifest.license === 'string' ? manifest.license : ''
      if (!license) {
        const reviewed = reviewedMissingDeclarations.get(identity)
        let licenseText = ''
        for (const fileName of ['LICENSE', 'license']) {
          try {
            licenseText = readFileSync(join(modulePath, fileName), 'utf8')
            break
          } catch { /* handled below */ }
        }
        if (!reviewed || !reviewed.evidence.test(licenseText)) failures.push(`${identity}: missing license declaration`)
      }
      else if (denied.test(license)) failures.push(`${identity}: prohibited license declaration`)
    }
    try {
      inspectModules(join(modulePath, 'node_modules'))
    } catch (error) {
      if (error?.code !== 'ENOENT') throw error
    }
  }
}

inspectModules(new URL('./node_modules', import.meta.url).pathname)
if (failures.length) throw new Error([...new Set(failures)].sort().join('\n'))
console.log(`Diagram renderer dependency license policy passed for ${seen.size} package versions.`)
