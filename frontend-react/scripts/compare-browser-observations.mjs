import { readFile, writeFile } from 'node:fs/promises'

async function observation(filename) {
  const report = JSON.parse(await readFile(filename, 'utf8'))
  const found = []
  function visit(suites) {
    for (const suite of suites ?? []) {
      for (const spec of suite.specs ?? []) {
        if (!spec.title.includes('@observations')) continue
        for (const test of spec.tests ?? []) {
          for (const result of test.results ?? []) {
            if (result.status !== 'passed') continue
            for (const attachment of result.attachments ?? []) {
              if (attachment.name === 'browser-observation.json' && attachment.body) found.push(JSON.parse(Buffer.from(attachment.body, 'base64').toString('utf8')))
            }
          }
        }
      }
      visit(suite.suites)
    }
  }
  visit(report.suites)
  if (found.length !== 1 || found[0].schema !== 1) throw new Error(`${filename}: require exactly one successful, supported @observations result`)
  return found[0]
}

function summarize(data, phase) {
  const requests = data.requests.filter(request => request.phase === phase)
  const groups = new Map()
  for (const request of requests) {
    const key = `${request.method} ${request.endpoint}`
    const group = groups.get(key) ?? { count: 0, failed: 0, bytes: 0, statuses: {}, milliseconds: [] }
    group.count++
    group.failed += Number(request.failed)
    group.bytes += request.bytes
    const status = request.status ?? 'no-response'
    group.statuses[status] = (group.statuses[status] ?? 0) + 1
    group.milliseconds.push(request.milliseconds)
    groups.set(key, group)
  }
  const endpoints = Object.fromEntries([...groups].sort(([a], [b]) => a.localeCompare(b)).map(([key, group]) => {
    group.milliseconds.sort((a, b) => a - b)
    const { milliseconds, ...rest } = group
    return [key, { ...rest, median_ms: milliseconds[Math.floor(milliseconds.length / 2)], p95_ms: milliseconds[Math.ceil(milliseconds.length * 0.95) - 1] }]
  }))
  return { duration_ms: data.windows.find(window => window.name === phase).milliseconds, requests: requests.length, failed: requests.filter(request => request.failed).length, bytes: requests.reduce((sum, request) => sum + request.bytes, 0), endpoints }
}

const [beforeFile, afterFile, outputFile] = process.argv.slice(2)
if (!beforeFile || !afterFile || !outputFile) throw new Error('Usage: node scripts/compare-browser-observations.mjs BEFORE/results.json AFTER/results.json OUTPUT.json')
const [before, after] = await Promise.all([observation(beforeFile), observation(afterFile)])
const phases = before.windows.map(window => window.name)
if (JSON.stringify(phases) !== JSON.stringify(after.windows.map(window => window.name))) throw new Error('Observation windows differ')
if (before.browser !== after.browser || JSON.stringify(before.viewport) !== JSON.stringify(after.viewport)) throw new Error('Browser or viewport differs')
const result = {
  schema: 1,
  before: { source: beforeFile, image_id: before.image_id, run_id: before.run_id, context: before.context, incomplete_requests: before.incomplete_requests },
  after: { source: afterFile, image_id: after.image_id, run_id: after.run_id, context: after.context, incomplete_requests: after.incomplete_requests },
  browser: before.browser,
  viewport: before.viewport,
  limitations: 'Separate owned flat worlds may have different seeds, geometry and bytes. Recorded requests include navigation cancellation. One sample per build is observational, without a statistical performance or regression threshold; compare completed requests and idle windows separately.',
  phases: Object.fromEntries(phases.map(phase => {
    const previous = summarize(before, phase)
    const current = summarize(after, phase)
    return [phase, { before: previous, after: current, delta: { requests: current.requests - previous.requests, failed: current.failed - previous.failed, bytes: current.bytes - previous.bytes, duration_ms: current.duration_ms - previous.duration_ms } }]
  })),
}
await writeFile(outputFile, JSON.stringify(result, null, 2) + '\n')
process.stdout.write(`Browser observation comparison written to ${outputFile}\n`)
