import { spawnSync } from 'node:child_process'
import { readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import openapiTS, { astToString } from 'openapi-typescript'
import { selectSchemaClosure } from './schema-closure.mjs'

const root = fileURLToPath(new URL('../', import.meta.url))
const exportCode = `
import json
from tests.support.environment import configure_test_environment
with configure_test_environment():
    from app.main import create_api_app
    from app.runtime import Runtime
    print(json.dumps(create_api_app(Runtime()).openapi()))
`
const command = process.platform === 'win32'
  ? ['wsl.exe', '--distribution', process.env.MC_ADMIN_WSL_DISTRO ?? 'Debian', '--cd', path.resolve(root, '..'), '--exec', 'env', ...(process.env.MC_ADMIN_LINUX_VENV ? [`MC_ADMIN_LINUX_VENV=${process.env.MC_ADMIN_LINUX_VENV}`] : []), 'bash', 'scripts/dev/backend.sh', 'run', 'python', '-c', exportCode]
  : ['uv', 'run', '--locked', 'python', '-c', exportCode]
const exported = spawnSync(command[0], command.slice(1), { cwd: path.resolve(root, '../backend'), encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 })
if (exported.error) throw exported.error
if (exported.status !== 0) throw new Error(`Isolated OpenAPI export failed:\n${exported.stderr}`)
const schema = JSON.parse(exported.stdout)
const components = selectSchemaClosure(schema.components?.schemas, ['UserPublic', 'UserCreate', 'LoginResponse'])
const generated = '// Generated from the backend OpenAPI dependency closure; run pnpm generate:contracts.\n' +
  astToString(await openapiTS({ openapi: schema.openapi, info: schema.info, paths: {}, components: { schemas: components } }))
const output = path.join(root, 'src/features/users/generated/api.ts')
if (process.argv.includes('--check')) {
  if (await readFile(output, 'utf8') !== generated) throw new Error('User API contracts are stale; run pnpm generate:contracts')
  console.log('User API contracts match the isolated backend OpenAPI schema.')
} else {
  await writeFile(output, generated)
  console.log('Generated user API contracts from the isolated backend OpenAPI schema.')
}
