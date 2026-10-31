import assert from 'node:assert/strict'
import { mkdtemp, writeFile, chmod, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { hostPath, requirePrivateFile, spawnHost, within } from './host.ts'

test('owned directory confinement rejects siblings and parent traversal', () => {
  const root = path.resolve('owned/runtime')
  assert.equal(within(root, path.join(root, 'server/file')), true)
  assert.equal(within(root, root), false)
  assert.equal(within(root, path.resolve('owned/runtime-other/file')), false)
  assert.equal(within(root, path.resolve('owned/private')), false)
})

test('host subprocess preserves argument bytes and propagates failure', async () => {
  if (process.platform === 'win32') process.env.MC_ADMIN_WSL_DISTRO ??= 'Debian'
  const argument = 'space \' quote " $ literal'
  const child = spawnHost('sh', ['-c', 'printf "%s" "$1"; exit 19', 'test', argument])
  let output = ''
  child.stdout.on('data', value => { output += value })
  const code = await new Promise((resolve, reject) => { child.on('error', reject); child.on('close', resolve) })
  assert.equal(code, 19)
  assert.equal(output, argument)
})

test('private credentials are checked on the owning filesystem', { skip: process.platform === 'win32' }, async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'browser-host-'))
  const file = path.join(directory, 'fixture.json')
  try {
    await writeFile(file, '{}', { mode: 0o600 })
    await requirePrivateFile(file)
    await chmod(file, 0o644)
    await assert.rejects(requirePrivateFile(file), /private file permissions/)
  } finally {
    await rm(directory, { recursive: true })
  }
})

test('Windows maps Linux fixture paths through the explicitly selected distribution', { skip: process.platform !== 'win32' }, () => {
  process.env.MC_ADMIN_WSL_DISTRO = 'Debian'
  assert.equal(hostPath('/root/owned server/file'), '\\\\wsl.localhost\\Debian\\root\\owned server\\file')
  assert.equal(hostPath('D:\\project'), 'D:\\project')
})
