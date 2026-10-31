import { spawn, spawnSync } from 'node:child_process'
import path from 'node:path'
import { chown, stat } from 'node:fs/promises'

function distribution() {
  const name = process.env.MC_ADMIN_WSL_DISTRO
  if (!name || /[\\/]/.test(name)) throw new Error('Windows browser tests require MC_ADMIN_WSL_DISTRO from their WSL owner.')
  return name
}

export function hostPath(value: string): string {
  if (process.platform !== 'win32' || !value.startsWith('/')) return value
  return `\\\\wsl.localhost\\${distribution()}${value.replaceAll('/', '\\')}`
}

function linuxPath(value: string): string {
  const prefix = `\\\\wsl.localhost\\${distribution()}\\`
  if (!value.startsWith(prefix)) throw new Error('Expected a path in the owning WSL distribution.')
  return '/' + value.slice(prefix.length).replaceAll('\\', '/')
}

function hostCommand(command: string, args: string[]) {
  return process.platform === 'win32'
    ? ['wsl.exe', '--distribution', distribution(), '--exec', command, ...args]
    : [command, ...args]
}

export function spawnHost(command: string, args: string[]) {
  const invocation = hostCommand(command, args)
  return spawn(invocation[0], invocation.slice(1), { stdio: 'pipe' })
}

function runHost(command: string, args: string[]) {
  const invocation = hostCommand(command, args)
  const result = spawnSync(invocation[0], invocation.slice(1), { encoding: 'utf8' })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error(`Owned host command failed: ${command}: ${result.stderr}`)
  return result.stdout.trim()
}

export async function requirePrivateFile(source: string) {
  const mode = process.platform === 'win32'
    ? Number.parseInt(runHost('stat', ['-c', '%a', '--', linuxPath(source)]), 8)
    : (await stat(source)).mode
  if (!Number.isFinite(mode) || mode & 0o077) throw new Error('Browser fixture credentials must have private file permissions.')
}

export async function copyOwner(source: string, destinations: string[]) {
  if (process.platform === 'win32') {
    if (runHost('id', ['-u']) === '0') runHost('chown', ['--reference', linuxPath(source), '--', ...destinations.map(linuxPath)])
  } else if (process.getuid?.() === 0) {
    const owner = await stat(source)
    for (const destination of destinations) await chown(destination, owner.uid, owner.gid)
  }
}

export function within(directory: string, candidate: string) {
  const relative = path.relative(directory, candidate)
  return relative !== '' && relative !== '..' && !relative.startsWith('..' + path.sep) && !path.isAbsolute(relative)
}
