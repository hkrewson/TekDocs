import { execFile } from 'node:child_process'
import { constants, readdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { promisify } from 'node:util'
import path from 'node:path'

const execFileAsync = promisify(execFile)
const jobRoot = '/jobs'
// Read from the package that is actually installed rather than restating it here. A
// hardcoded copy drifts the moment a dependency update lands, and this value is recorded
// in signed publication manifests — a stale constant would attest a renderer that never
// ran, which is worse than no attestation at all.
const rendererVersion = (() => {
  const manifest = JSON.parse(readFileSync('/renderer/node_modules/@mermaid-js/mermaid-cli/package.json', 'utf8'))
  return `${manifest.name}@${manifest.version}`
})()
const jobPattern = /^[0-9a-f]{32}$/
const maximumOutputBytes = 2 * 1024 * 1024
const maximumPngBytes = 5 * 1024 * 1024
const maximumJobs = 8
const staleMilliseconds = 5 * 60 * 1000

// A job can fail six operationally different ways. Reporting one flat code for all of
// them means an operator reading container logs cannot tell a Chromium launch failure
// from a diagram that renders too large, which is exactly the position this renderer
// put us in once.
//
// The code is all that is reported. Renderer stderr can echo the diagram source, and
// that source is customer content, so it never reaches the log or the result file.
const failureCodesByMessage = new Map([
  ['invalid request', 'invalid_request'],
  ['incomplete render', 'incomplete_render'],
  ['oversized render', 'oversized_render'],
  ['incomplete raster', 'incomplete_raster'],
  ['oversized raster', 'oversized_raster'],
])

function failureCode(error) {
  const message = error && typeof error.message === 'string' ? error.message : ''
  const mapped = failureCodesByMessage.get(message)
  if (mapped) return mapped
  if (error && (error.killed === true || error.signal === 'SIGTERM' || error.code === 'ETIMEDOUT')) {
    return 'renderer_timeout'
  }
  if (error && typeof error.cmd === 'string' && error.cmd.includes('rsvg-convert')) return 'raster_failed'
  return 'render_failed'
}

function atomicJson(jobDirectory, payload) {
  const temporary = path.join(jobDirectory, '.result.json')
  writeFileSync(temporary, `${JSON.stringify(payload)}\n`, { encoding: 'utf8', mode: 0o600 })
  renameSync(temporary, path.join(jobDirectory, 'result.json'))
}

function safeFiles(jobDirectory, suffix) {
  return readdirSync(jobDirectory)
    .filter((name) => /^output-[1-9][0-9]*\.(svg|png)$/.test(name) && name.endsWith(suffix))
    .sort((left, right) => Number(left.match(/[0-9]+/)?.[0]) - Number(right.match(/[0-9]+/)?.[0]))
}

async function processJob(jobName) {
  const jobDirectory = path.join(jobRoot, jobName)
  const ready = path.join(jobDirectory, 'ready')
  const processing = path.join(jobDirectory, 'processing')
  try {
    renameSync(ready, processing)
  } catch {
    return
  }
  try {
    const request = JSON.parse(readFileSync(path.join(jobDirectory, 'request.json'), 'utf8'))
    if (!Number.isInteger(request.count) || request.count < 1 || request.count > 20) throw new Error('invalid request')
    await execFileAsync(
      '/renderer/node_modules/.bin/mmdc',
      [
        '--input', path.join(jobDirectory, 'input.md'),
        '--output', path.join(jobDirectory, 'output.md'),
        '--configFile', '/renderer/mermaid-config.json',
        '--puppeteerConfigFile', '/renderer/puppeteer-config.json',
        '--backgroundColor', 'white',
        '--width', '1200',
        '--height', '800',
      ],
      { timeout: 15000, maxBuffer: 64 * 1024, env: { ...process.env, NO_PROXY: '*', no_proxy: '*' } },
    )
    const svgFiles = safeFiles(jobDirectory, '.svg')
    if (svgFiles.length !== request.count) throw new Error('incomplete render')
    for (const svgName of svgFiles) {
      const svgPath = path.join(jobDirectory, svgName)
      if (statSync(svgPath).size > maximumOutputBytes) throw new Error('oversized render')
      const pngName = svgName.replace(/\.svg$/, '.png')
      const pngPath = path.join(jobDirectory, pngName)
      await execFileAsync('/usr/bin/rsvg-convert', ['--background-color', 'white', '--output', pngPath, svgPath], {
        timeout: 5000,
        maxBuffer: 16 * 1024,
      })
      if (statSync(pngPath).size > maximumPngBytes) throw new Error('oversized raster')
    }
    if (safeFiles(jobDirectory, '.png').length !== request.count) throw new Error('incomplete raster')
    atomicJson(jobDirectory, { status: 'ok', count: request.count, renderer: rendererVersion })
  } catch (error) {
    const code = failureCode(error)
    const status = error && Number.isInteger(error.code) ? ` exit=${error.code}` : ''
    process.stderr.write(`diagram render failed: ${code}${status}\n`)
    atomicJson(jobDirectory, { status: 'error', code })
  }
}

function removeStaleJobs() {
  const now = Date.now()
  for (const name of readdirSync(jobRoot)) {
    if (!jobPattern.test(name)) continue
    const target = path.join(jobRoot, name)
    try {
      if (now - statSync(target).mtimeMs > staleMilliseconds) rmSync(target, { recursive: true, force: true })
    } catch {
      // Another process may have completed cleanup.
    }
  }
}

async function cycle() {
  removeStaleJobs()
  const jobs = readdirSync(jobRoot).filter((name) => jobPattern.test(name)).slice(0, maximumJobs)
  for (const job of jobs) await processJob(job)
  writeFileSync(path.join(jobRoot, '.renderer-ready'), `${Date.now()}\n`, { encoding: 'utf8', mode: 0o600 })
}

let running = false
async function scheduledCycle() {
  if (running) return
  running = true
  try {
    await cycle()
  } finally {
    running = false
  }
}

await scheduledCycle()
setInterval(() => { void scheduledCycle() }, 100)
