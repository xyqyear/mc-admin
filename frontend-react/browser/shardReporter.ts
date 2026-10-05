import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import type { FullConfig, FullResult, Reporter, Suite, TestCase, TestResult } from '@playwright/test/reporter'

export function caseIdentity(test: TestCase, rootDir = process.cwd()) {
  const project = test.parent.project()?.name ?? ''
  const file = path.relative(rootDir, test.location.file).split(path.sep).join('/')
  const titles = test.titlePath().slice(3)
  const groups = test.annotations.filter(row => row.type === 'shard_group').map(row => {
    if (!row.description) throw new Error('shard_group requires a stable group name')
    return `shared:${project}:${row.description}`
  })
  if (!test.annotations.some(row => row.type === 'shard_isolation' && row.description === 'independent')) groups.push(`file:${project}:${file}`)
  return { id: JSON.stringify([project, file, ...titles]), project, file, titles, groups }
}

function writeReport(filename: string | undefined, value: unknown) {
  if (!filename) return
  mkdirSync(path.dirname(filename), { recursive: true })
  writeFileSync(filename, JSON.stringify(value, null, 2) + '\n')
}

export default class ShardReporter implements Reporter {
  private rootDir = process.cwd()
  private cases: ReturnType<typeof caseIdentity>[] = []
  private results: Array<{ id: string; status: string; retry: number; seconds: number }> = []

  onBegin(config: FullConfig, suite: Suite) {
    if (config.workers !== 1 || config.fullyParallel || config.projects.some(project => project.retries !== 0)) throw new Error('Owned browser shards require one serial worker and no retries')
    this.rootDir = config.rootDir
    this.cases = suite.allTests().map(test => caseIdentity(test, this.rootDir))
    if (new Set(this.cases.map(row => row.id)).size !== this.cases.length) throw new Error('Browser case identities must be unique')
    writeReport(process.env.BROWSER_INVENTORY_PATH, { schema_version: 1, cases: this.cases })
  }

  onTestEnd(test: TestCase, result: TestResult) {
    this.results.push({ id: caseIdentity(test, this.rootDir).id, status: result.status, retry: result.retry, seconds: result.duration / 1000 })
  }

  onEnd(result: FullResult) {
    writeReport(process.env.BROWSER_SHARD_REPORT, {
      schema_version: 1,
      plan_sha256: process.env.BROWSER_PLAN_SHA256,
      history_sha256: process.env.BROWSER_HISTORY_SHA256,
      source_sha: process.env.BROWSER_SOURCE_SHA,
      shard: Number(process.env.BROWSER_SHARD),
      status: result.status,
      selected: this.cases.map(row => row.id),
      results: this.results,
      command_seconds: result.duration / 1000,
    })
  }
}
