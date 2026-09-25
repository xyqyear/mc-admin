import test from 'node:test'
import assert from 'node:assert/strict'
import { importBoundaryViolation, moduleReferences } from './import-boundaries.mjs'
import { selectSchemaClosure } from './schema-closure.mjs'

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
