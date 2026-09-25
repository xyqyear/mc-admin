import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { importBoundaryViolation, moduleReferences } from './import-boundaries.mjs'

const root = fileURLToPath(new URL('../src/', import.meta.url))
async function files(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  return (await Promise.all(entries.map(entry => entry.isDirectory() ? files(path.join(directory, entry.name)) : path.join(directory, entry.name)))).flat()
}
const errors = []
let count = 0
for (const filename of await files(root)) {
  if (!/\.[jt]sx?$/.test(filename)) continue
  const from = path.relative(root, filename)
  if (from.includes('.test.') || from.startsWith('test/')) continue
  count++
  for (const reference of moduleReferences(filename, await readFile(filename, 'utf8'))) {
    const to = reference.name.startsWith('@/') ? reference.name.slice(2)
      : reference.name.startsWith('.') ? path.relative(root, path.resolve(path.dirname(filename), reference.name)) : null
    if (!to) continue
    const violation = importBoundaryViolation(from, to)
    if (violation) errors.push(`${from}:${reference.line}: ${reference.name}: ${violation}`)
  }
}
if (errors.length) {
  console.error(errors.join('\n'))
  process.exitCode = 1
} else console.log(`Frontend import boundaries passed (${count} production files).`)
