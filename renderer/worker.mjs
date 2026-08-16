import { execFile } from 'node:child_process'
import { constants, readdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { promisify } from 'node:util'
import path from 'node:path'

const execFileAsync = promisify(execFile)
const jobRoot = '/jobs'
const rendererVersion = '@mermaid-js/mermaid-cli@11.16.0'
const jobPattern = /^[0-9a-f]{32}$/
const maximumOutputBytes = 2 * 1024 * 1024
const maximumPngBytes = 5 * 1024 * 1024
const maximumJobs = 8
const staleMilliseconds = 5 * 60 * 1000

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
  } catch {
    atomicJson(jobDirectory, { status: 'error', code: 'render_failed' })
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
