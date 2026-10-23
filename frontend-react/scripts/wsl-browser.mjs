import { once } from 'node:events'
import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'
import path from 'node:path'

const input = createInterface({ input: process.stdin })
const [line] = await once(input, 'line')
if (line !== 'start') throw new Error('The Windows browser process requires its owning job.')
input.close()
const cli = path.resolve('node_modules/@playwright/test/cli.js')
const child = spawn(process.execPath, [cli, 'test', ...process.argv.slice(2)], { stdio: 'inherit' })
child.on('error', error => { console.error(error); process.exitCode = 1 })
child.on('exit', code => { process.exitCode = code ?? 1 })
process.stdin.unref()
