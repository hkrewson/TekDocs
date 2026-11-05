import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import test from 'node:test'
import { attachPublicationDiagnostics } from '../../e2e/publicationDiagnostics.ts'

test('native workflow and password-confirmation diagnostics never read or retain request values', () => {
  const page = new EventEmitter(), lines = []
  const diagnostic = attachPublicationDiagnostics(page, { scenario: 'native_publications', write: line => lines.push(line) })
  for (const [method, path] of [
    ['POST', '/api/v1/workspaces/msp/repository-publication-evidence'],
    ['GET', '/api/v1/workspaces/organizations/private-org/repository-publication-evidence/private-evidence/workflow'],
    ['POST', '/api/v1/workspaces/organizations/private-org/repository-publication-evidence/private-evidence/package/static-publication/delivery-authorization'],
    ['POST', '/_allauth/browser/v1/auth/reauthenticate'],
  ]) {
    const request = { url: () => `http://localhost${path}?private-query=private-value`, method: () => method, headers: () => { throw new Error('Headers must not be read') }, postData: () => { throw new Error('Password must not be read') } }
    page.emit('request', request)
    page.emit('response', { request: () => request, status: () => 403 })
    page.emit('requestfinished', request)
  }
  diagnostic.finish('failed')
  const report = JSON.parse(lines[0])
  assert.equal(report.scenario, 'native_publications')
  assert.deepEqual(report.events.filter(event => event.event === 'response').map(event => event.phase), ['native_snapshot', 'native_workflow', 'native_delivery', 'native_reauthentication'])
  assert.ok(!lines[0].includes('private-') && !lines[0].includes('localhost'))
  diagnostic.dispose()
})

test('primary-file diagnostics distinguish intake and download without reading file values', () => {
  const page = new EventEmitter(), lines = []
  const diagnostic = attachPublicationDiagnostics(page, { scenario: 'native_primary_files', write: line => lines.push(line) })
  for (const [method, path] of [
    ['GET', '/api/v1/workspaces/organizations/private-org/content-graph/authoring/private-document/primary-file'],
    ['POST', '/api/v1/workspaces/msp/content-graph/authoring/private-document/primary-file'],
    ['GET', '/api/v1/workspaces/organizations/private-org/content-graph/documents/private-document/attachments/private-file/download'],
  ]) {
    const request = { url: () => 'http://localhost' + path + '?filename=private-value', method: () => method,
      headers: () => { throw new Error('Headers must not be read') }, postData: () => { throw new Error('File bytes must not be read') } }
    page.emit('request', request)
    page.emit('response', { request: () => request, status: () => 409 })
    page.emit('requestfinished', request)
  }
  diagnostic.finish('failed')
  const report = JSON.parse(lines[0])
  assert.equal(report.scenario, 'native_primary_files')
  assert.deepEqual(report.events.filter(event => event.event === 'response').map(event => event.phase), ['primary_file_read', 'primary_file_write', 'managed_file_download'])
  for (const value of ['localhost', 'private-', 'filename', 'content-graph']) assert.ok(!lines[0].includes(value))
  diagnostic.dispose()
})

test('a pending Git document read is visible without retaining document or query values', () => {
  const page = new EventEmitter(), lines = []
  let time = 0
  const diagnostic = attachPublicationDiagnostics(page, {
    scenario: 'history_templates', now: () => time, write: line => lines.push(line),
  })
  for (const path of [
    '/api/v1/workspaces/organizations/private-organization/documents',
    '/api/v1/workspaces/organizations/private-organization/documents/private-document',
  ]) {
    const request = { url: () => `http://localhost${path}?caption=private-caption`, method: () => 'GET' }
    page.emit('request', request)
    page.emit('response', { request: () => request, status: () => 200 })
    page.emit('requestfinished', request)
  }
  const request = {
    url: () => 'http://localhost/api/v1/workspaces/organizations/private-organization/content-graph/documents/private-content?caption=private-caption',
    method: () => 'GET',
    headers: () => { throw new Error('Session headers must not be read') },
    postData: () => { throw new Error('Content must not be read') },
  }
  time = 100
  page.emit('request', request)
  time = 5100
  diagnostic.finish('failed')
  const report = JSON.parse(lines[0])
  assert.deepEqual(report.events.filter(event => event.event === 'request').map(event => event.phase), [
    'document_list', 'document_read', 'git_document_read',
  ])
  assert.deepEqual(report.pending, [{ phase: 'git_document_read', age_ms: 5000 }])
  for (const value of ['localhost', 'private-', 'caption', 'content-graph']) assert.ok(!lines[0].includes(value))
  diagnostic.dispose()
})

test('client workflow failures identify the boundary without retaining identities or session values', () => {
  const page = new EventEmitter(), lines = []
  const diagnostic = attachPublicationDiagnostics(page, { scenario: 'client_publications', write: line => lines.push(line) })
  for (const [method, path] of [
    ['GET', '/workspaces/organizations/private-organization'],
    ['GET', '/portal/documents/private-publication'],
    ['POST', '/workspaces/organizations/private-organization/documents/private-document/publications/private-publication/approve'],
    ['POST', '/workspaces/organizations/private-organization/documents/private-document/publications/private-publication/withdraw'],
  ]) {
    const request = {
      url: () => `http://localhost/api/v1${path}?private-key=private-value`, method: () => method,
      headers: () => { throw new Error('Session headers must not be read') },
      postData: () => { throw new Error('Content must not be read') },
    }
    page.emit('request', request)
    page.emit('response', { request: () => request, status: () => 404 })
    page.emit('requestfinished', request)
  }
  diagnostic.finish('failed')
  const report = JSON.parse(lines[0])
  assert.equal(report.scenario, 'client_publications')
  assert.deepEqual(report.events.filter(event => event.event === 'response').map(event => [event.phase, event.status]), [
    ['workspace_read', 404], ['portal_read', 404], ['publication_approve', 404], ['publication_withdraw', 404],
  ])
  assert.ok(!lines[0].includes('private-'))
  assert.ok(!lines[0].includes('localhost'))
  diagnostic.dispose()
})

test('failed acceptance reports public phase timings without request values', () => {
  const page = new EventEmitter()
  const lines = []
  let time = 0
  const diagnostic = attachPublicationDiagnostics(page, {
    scenario: 'history_templates', now: () => time, write: line => lines.push(line),
  })
  const request = {
    url: () => 'http://localhost/api/v1/workspaces/organizations/fixture-organization/documents/from-template?caption=unpublished-heading',
    method: () => 'POST',
    headers: () => { throw new Error('Headers must not be read') },
    postData: () => { throw new Error('Bodies must not be read') },
  }
  diagnostic.mark('template')
  time = 10
  page.emit('request', request)
  time = 45
  page.emit('response', { request: () => request, status: () => 201 })
  time = 50
  page.emit('requestfinished', request)
  time = 150
  diagnostic.finish('timedOut', { navigationPrompt: true })
  assert.equal(lines.length, 1)
  const report = JSON.parse(lines[0])
  assert.equal(report.scenario, 'history_templates')
  assert.equal(report.elapsed_ms, 150)
  assert.deepEqual(report.events, [
    { event: 'milestone', phase: 'template', ms: 0 },
    { event: 'request', phase: 'template_create', ms: 10 },
    { event: 'response', phase: 'template_create', ms: 45, status: 201, elapsed_ms: 35 },
    { event: 'finished', phase: 'template_create', ms: 50, elapsed_ms: 40 },
  ])
  assert.deepEqual(report.pending, [])
  assert.deepEqual(report.visible, { navigationPrompt: true })
  for (const value of ['localhost', 'fixture-organization', 'unpublished-heading', 'caption']) assert.ok(!lines[0].includes(value))
  diagnostic.dispose()
})

test('a pending PDF request is distinguishable from an observed download', () => {
  const page = new EventEmitter(), lines = []
  let time = 0
  const diagnostic = attachPublicationDiagnostics(page, { now: () => time, write: line => lines.push(line) })
  const request = { url: () => 'http://localhost/api/v1/documents/fixture/publications/retained/export?export_format=pdf', method: () => 'GET' }
  page.emit('request', request)
  time = 5
  page.emit('response', { request: () => request, status: () => 200 })
  time = 500
  diagnostic.finish('timedOut', { pdfDownload: true })
  const report = JSON.parse(lines[0])
  assert.deepEqual(report.pending, [{ phase: 'download_pdf', age_ms: 500 }])
  assert.equal(report.events.some(event => event.event === 'download'), false)
  assert.equal(report.events.find(event => event.event === 'response').status, 200)
  diagnostic.dispose()
})

test('Chromium download hand-off does not itself report a failed acceptance', () => {
  const page = new EventEmitter(), lines = []
  const diagnostic = attachPublicationDiagnostics(page, { write: line => lines.push(line) })
  const request = { url: () => 'http://localhost/api/v1/documents/fixture/publications/retained/export?export_format=pdf', method: () => 'GET' }
  page.emit('request', request)
  page.emit('response', { request: () => request, status: () => 200 })
  page.emit('requestfailed', request)
  page.emit('download', { suggestedFilename: () => { throw new Error('Filenames must not be read') } })
  diagnostic.finish('passed')
  assert.deepEqual(lines, [])
  diagnostic.dispose()
  for (const event of ['request', 'response', 'requestfinished', 'requestfailed', 'download', 'dialog', 'pageerror']) assert.equal(page.listenerCount(event), 0)
})

test('unknown labels, snapshot values and unrelated routes cannot disclose content', () => {
  const page = new EventEmitter(), lines = []
  const diagnostic = attachPublicationDiagnostics(page, { scenario: 'unpublished-heading', write: line => lines.push(line) })
  diagnostic.mark('unpublished-heading')
  page.emit('request', { url: () => 'not a URL', method: () => 'POST' })
  page.emit('request', { url: () => 'http://localhost/unpublished-heading', method: () => 'POST' })
  diagnostic.finish('unpublished-heading', { navigationPrompt: 'unpublished-heading', privateCaption: 'unpublished-heading', useTemplate: false })
  const report = JSON.parse(lines[0])
  assert.equal(report.scenario, 'unknown')
  assert.equal(report.result, 'unknown')
  assert.deepEqual(report.visible, { useTemplate: false })
  assert.deepEqual(report.events, [])
  assert.ok(!lines[0].includes('unpublished-heading'))
  diagnostic.dispose()
})

test('failure buffers stay bounded under an unfinished request burst', () => {
  const page = new EventEmitter(), lines = []
  const diagnostic = attachPublicationDiagnostics(page, { write: line => lines.push(line) })
  for (let index = 0; index < 1000; index += 1) {
    page.emit('request', { url: () => `http://localhost/api/v1/documents/from-template?caption=unpublished-${index}`, method: () => 'POST' })
  }
  diagnostic.finish('timedOut')
  const report = JSON.parse(lines[0])
  assert.ok(report.events.length <= 128)
  assert.ok(report.pending.length <= 32)
  assert.ok(report.dropped_events > 0)
  assert.ok(report.evicted_requests > 0)
  assert.ok(lines[0].length < 32768)
  assert.ok(!lines[0].includes('unpublished-'))
  diagnostic.dispose()
})

test('skipped runs stay silent and failure reporting is emitted only once', () => {
  const page = new EventEmitter(), lines = []
  const skipped = attachPublicationDiagnostics(page, { write: line => lines.push(line) })
  skipped.finish('skipped')
  skipped.dispose()
  assert.deepEqual(lines, [])
  const failed = attachPublicationDiagnostics(page, { write: line => lines.push(line) })
  page.emit('dialog', { message: () => { throw new Error('Dialog text must not be read') } })
  page.emit('pageerror', new Error('unpublished-heading'))
  failed.finish('failed')
  failed.finish('failed')
  assert.equal(lines.length, 1)
  assert.ok(!lines[0].includes('unpublished-heading'))
  assert.deepEqual(JSON.parse(lines[0]).events.map(event => event.event), ['dialog', 'page_error'])
  failed.dispose()
})


test('native key reads never retain searches or pending target identities', () => {
  const page = new EventEmitter(), lines = []
  const diagnostic = attachPublicationDiagnostics(page, { scenario: 'native_keys', write: line => lines.push(line) })
  const request = { url: () => 'http://localhost/api/v1/workspaces/msp/content-graph/authoring/private-document/keys?q=private-search&target_id=private-target', method: () => 'GET',
    headers: () => { throw new Error('Headers must not be read') }, postData: () => { throw new Error('Body must not be read') } }
  page.emit('request', request)
  page.emit('response', { request: () => request, status: () => 409 })
  page.emit('requestfinished', request)
  diagnostic.finish('failed')
  const report = JSON.parse(lines[0])
  assert.equal(report.scenario, 'native_keys')
  assert.equal(report.events.find(event => event.event === 'response').phase, 'native_keys_read')
  for (const value of ['localhost', 'private-', 'target_id', 'content-graph']) assert.ok(!lines[0].includes(value))
  diagnostic.dispose()
})

test('native template diagnostics distinguish scoped operations without recording reviewed source', () => {
  const page = new EventEmitter(), lines = []
  const diagnostic = attachPublicationDiagnostics(page, { scenario: 'native_templates', write: line => lines.push(line) })
  for (const [method, path] of [
    ['GET', '/api/v1/workspaces/msp/content-graph/authoring/private-document/template'],
    ['POST', '/api/v1/workspaces/organizations/private-org/content-graph/authoring/private-document/template'],
    ['POST', '/api/v1/workspaces/organizations/private-org/content-graph/template-enrollments'],
  ]) {
    const request = { url: () => `http://localhost${path}?private-query=value`, method: () => method,
      headers: () => { throw new Error('Headers must not be read') }, postData: () => { throw new Error('Reviewed text must not be read') } }
    page.emit('request', request)
    page.emit('response', { request: () => request, status: () => 409 })
    page.emit('requestfinished', request)
  }
  diagnostic.finish('failed')
  const report = JSON.parse(lines[0])
  assert.equal(report.scenario, 'native_templates')
  assert.deepEqual(report.events.filter(event => event.event === 'response').map(event => event.phase), ['native_template_read', 'native_template_write', 'native_template_enroll'])
  for (const value of ['localhost', 'private-', 'content-graph']) assert.ok(!lines[0].includes(value))
  diagnostic.dispose()
})


test('native source read diagnostics record safe status and only fixed editor state', () => {
  const page = new EventEmitter(), lines = []
  const diagnostic = attachPublicationDiagnostics(page, { scenario: 'native_templates', write: line => lines.push(line) })
  const request = { url: () => 'http://localhost/api/v1/workspaces/organizations/private-org/content-graph/authoring/private-doc?private=value', method: () => 'GET' }
  page.emit('request', request)
  page.emit('response', { request: () => request, status: () => 404 })
  diagnostic.finish('failed', { repositoryEditor: true, repositorySourceFailure: true, nativeLibrary: false, privateError: 'private-content' })
  const report = JSON.parse(lines[0])
  assert.equal(report.events.find(event => event.event === 'response').phase, 'native_source_read')
  assert.deepEqual(report.visible, { repositoryEditor: true, repositorySourceFailure: true, nativeLibrary: false })
  for (const value of ['localhost', 'private-', 'content-graph']) assert.ok(!lines[0].includes(value))
  diagnostic.dispose()
})

test('reader authentication boundaries retain status without inspecting account or session bodies', () => {
  const page = new EventEmitter(), lines = []
  const diagnostic = attachPublicationDiagnostics(page, { scenario: 'native_templates', write: line => lines.push(line) })
  for (const path of ['/_allauth/browser/v1/auth/session', '/api/v1/auth/context']) {
    const request = { url: () => 'http://localhost' + path, method: () => 'GET', headers: () => { throw new Error('No session headers') } }
    page.emit('request', request)
    page.emit('response', { request: () => request, status: () => 200, json: () => { throw new Error('No account payload') } })
    page.emit('requestfinished', request)
  }
  diagnostic.finish('failed')
  const report = JSON.parse(lines[0])
  assert.deepEqual(report.events.filter(event => event.event === 'response').map(event => event.phase), ['auth_session', 'auth_context'])
  assert.ok(!lines[0].includes('localhost') && !lines[0].includes('/api'))
  diagnostic.dispose()
})
