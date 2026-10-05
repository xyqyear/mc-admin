import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import ShardReporter, { caseIdentity } from './shardReporter.ts'

function declared(title, annotations = [], line = 391) {
  return { parent: { project: () => ({ name: 'chromium' }) }, location: { file: path.join(process.cwd(), 'browser/journeys.spec.ts'), line }, titlePath: () => ['', 'chromium', 'journeys.spec.ts', 'administration', title], annotations }
}

test('browser case identity distinguishes titles sharing a declaration line and survives line moves', () => {
  const independent = [{ type: 'shard_isolation', description: 'independent' }]
  const first = caseIdentity(declared('first', independent))
  assert.notEqual(first.id, caseIdentity(declared('second', independent)).id)
  assert.equal(first.id, caseIdentity(declared('first', independent, 500)).id)
  assert.deepEqual(first.groups, [])
})

test('browser grouping keeps undeclared files and explicit shared groups atomic', () => {
  assert.deepEqual(caseIdentity(declared('first')).groups, caseIdentity(declared('second')).groups)
  const annotations = [{ type: 'shard_group', description: 'serial-recovery' }]
  assert.ok(caseIdentity(declared('first', annotations)).groups.includes('shared:chromium:serial-recovery'))
})

test('browser reporter refuses shared-world parallelism and assertion retries', () => {
  for (const config of [{ workers: 2, fullyParallel: false, projects: [{ retries: 0 }] }, { workers: 1, fullyParallel: true, projects: [{ retries: 0 }] }, { workers: 1, fullyParallel: false, projects: [{ retries: 1 }] }]) {
    assert.throws(() => new ShardReporter().onBegin(config, { allTests: () => [] }), /serial worker and no retries/)
  }
})

test('browser reporter preserves selected identities, outcomes and frozen metadata in artifacts', t => {
  const directory = mkdtempSync(path.join(os.tmpdir(), 'browser-reporter-'))
  const variables = { BROWSER_INVENTORY_PATH: path.join(directory, 'inventory.json'), BROWSER_SHARD_REPORT: path.join(directory, 'report.json'), BROWSER_PLAN_SHA256: 'plan', BROWSER_HISTORY_SHA256: 'history', BROWSER_SOURCE_SHA: 'source', BROWSER_SHARD: '2' }
  const prior = Object.fromEntries(Object.keys(variables).map(key => [key, process.env[key]]))
  Object.assign(process.env, variables)
  t.after(() => {
    for (const [key, value] of Object.entries(prior)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
    rmSync(directory, { recursive: true, force: true })
  })
  const first = declared('first')
  const second = declared('second')
  const rootDir = path.join(process.cwd(), 'browser')
  const identities = [first, second].map(entry => caseIdentity(entry, rootDir))
  const reporter = new ShardReporter()
  reporter.onBegin({ rootDir, workers: 1, fullyParallel: false, projects: [{ retries: 0 }] }, { allTests: () => [first, second] })
  reporter.onTestEnd(first, { status: 'passed', retry: 0, duration: 1250 })
  reporter.onTestEnd(second, { status: 'failed', retry: 0, duration: 750 })
  reporter.onEnd({ status: 'failed', duration: 2500 })
  assert.equal(identities[0].file, 'journeys.spec.ts')
  assert.deepEqual(JSON.parse(readFileSync(variables.BROWSER_INVENTORY_PATH, 'utf8')).cases, identities)
  assert.deepEqual(JSON.parse(readFileSync(variables.BROWSER_SHARD_REPORT, 'utf8')), {
    schema_version: 1, plan_sha256: 'plan', history_sha256: 'history', source_sha: 'source', shard: 2, status: 'failed',
    selected: identities.map(entry => entry.id),
    results: [{ id: identities[0].id, status: 'passed', retry: 0, seconds: 1.25 }, { id: identities[1].id, status: 'failed', retry: 0, seconds: 0.75 }],
    command_seconds: 2.5,
  })
})
