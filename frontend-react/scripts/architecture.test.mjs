import test from 'node:test'
import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { createServer } from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'
import { importBoundaryViolation, moduleReferences } from './import-boundaries.mjs'
import { selectSchemaClosure } from './schema-closure.mjs'

test('shadcn CLI resolves shared paths and recognizes installed components', async (t) => {
  const root = fileURLToPath(new URL('../', import.meta.url))
  const registry = createServer((request, response) => {
    if (request.url !== '/r/index.json') {
      response.writeHead(404).end()
      return
    }
    response.setHeader('Content-Type', 'application/json')
    response.end(JSON.stringify([
      { name: 'button', type: 'registry:ui' },
      { name: 'sidebar', type: 'registry:ui' },
    ]))
  })
  await new Promise((resolve, reject) => {
    registry.once('error', reject)
    registry.listen(0, '127.0.0.1', resolve)
  })
  t.after(() => new Promise((resolve, reject) => {
    registry.close((error) => error ? reject(error) : resolve())
  }))

  const environment = { ...process.env }
  for (const name of ['TS_NODE_PROJECT', 'TS_NODE_BASEURL', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']) {
    delete environment[name]
  }
  environment.REGISTRY_URL = `http://127.0.0.1:${registry.address().port}/r`
  const { stdout } = await promisify(execFile)('pnpm', ['exec', 'shadcn', 'info', '--json'], {
    cwd: root,
    env: environment,
    encoding: 'utf8',
    timeout: 30_000,
  })
  const { config, components } = JSON.parse(stdout)

  assert.equal(config.resolvedPaths.ui, path.join(root, 'src/shared/ui'))
  assert.equal(config.resolvedPaths.utils, path.join(root, 'src/shared/lib/utils'))
  assert.equal(config.resolvedPaths.hooks, path.join(root, 'src/shared/hooks'))
  assert.ok(components.includes('button'))
  assert.ok(components.includes('sidebar'))
})

test('rejects reverse dependencies, old layers, and private cross-feature imports', () => {
  for (const [from, to] of [
    ['shared/http/api.ts', 'features/users/api'],
    ['features/files/api.ts', 'app/operations/OperationObserver'],
    ['features/files/FileBrowserScreen.tsx', 'features/servers/useServerDetailData'],
    ['features/servers/api.ts', 'features/servers/ui/ServerNameTag'],
    ['features/users/contracts.ts', 'features/users/auth'],
    ['App.tsx', 'hooks/api/serverApi'],
    ['features/files/FileBrowserScreen.tsx', 'features/servers/ServerDetailScreen'],
  ]) assert.ok(importBoundaryViolation(from, to), `${from} -> ${to}`)
})

test('allows explicit feature composition and local implementations', () => {
  for (const [from, to] of [
    ['App.tsx', 'features/users/LoginScreen'],
    ['app/operations/OperationObserver.tsx', 'features/files/operationResources'],
    ['features/files/commands.ts', 'features/tasks/downloads'],
    ['features/files/FileBrowserScreen.tsx', 'features/servers/ui/ServerNameTag'],
    ['features/files/FileBrowserScreen.tsx', 'features/files/useFileBrowser'],
    ['shared/http/api.ts', 'shared/utils/formatUtils'],
  ]) assert.equal(importBoundaryViolation(from, to), null)
})

test('checks imports, reexports, dynamic imports, and imported types', () => {
  assert.deepEqual(moduleReferences('example.ts', `import type { A } from '@/features/a/contracts';
export { B } from './b';
const page = import('../private');
type Value = import('./types').Value;`).map(reference => reference.name), [
    '@/features/a/contracts', './b', '../private', './types',
  ])
})

test('selects only the actual complete OpenAPI dependency closure', () => {
  const schemas = { Root: { type: 'object', properties: { role: { $ref: '#/components/schemas/Role' } } }, Role: { type: 'string', enum: ['admin'] }, Incomplete: {} }
  assert.deepEqual(Object.keys(selectSchemaClosure(schemas, ['Root'])), ['Root', 'Role'])
  for (const invalid of [
    {}, { type: 'object' }, { type: 'object', additionalProperties: true },
    { type: 'object', additionalProperties: {} }, { type: 'array' },
    { $ref: '#/components/schemas/Missing' }, { $ref: 'https://external/schema' },
  ]) assert.throws(() => selectSchemaClosure({ Root: invalid }, ['Root']))
})
