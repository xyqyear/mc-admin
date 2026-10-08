import { StrictMode } from 'react'
import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createOperationFeed } from '@/test/operations'
import { OperationObserver } from '@/app/operations/OperationObserver'
import { useUpdateModuleConfig, useResetModuleConfig } from '@/features/settings/commands'
import { useUpdateFile } from '@/features/files/commands'
import { FileSnapshotRecovery } from '@/features/files/components/FileSnapshotRecovery'
import FileSnapshotActions from '@/features/files/components/FileSnapshotActions'
import { FileBatchActions } from '@/features/files/components/FileBatchActions'
import type { Operation } from '@/shared/operations/contracts'
import { queryKeys } from '@/shared/http/api'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { useSnapshotRules, useSnapshotTarget } from './queries'
import { checkLogicalSnapshotPaths } from './targetRules'
import { fileSnapshotScope } from './commands'
import type { SnapshotTargetRules } from './contracts'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let reads: string[]
let generation: number
let rules: string[]
beforeEach(() => {
  client = createTestClient()
  reads = []
  generation = 1
  rules = ['config', 'world/private']
  server.use(
    http.get('*/api/servers/:id', ({ params }) => HttpResponse.json({ id: params.id, name: params.id, serverType: 'VANILLA', server_generation: generation })),
    http.get('*/api/snapshots/targets/rules', ({ request }) => {
      const id = new URL(request.url).searchParams.get('server_id')!
      reads.push(id)
      return HttpResponse.json({ server_id: id, server_generation: generation, ignored_paths: rules, rules_version: 'v' + generation + ':' + rules.join(',') })
    }),
    http.get('*/api/snapshots/restorations/active', () => HttpResponse.json({ restorations: [], total: 0 })),
  )
})
afterEach(() => { client.clear(); server.resetHandlers(); vi.useRealTimers() })
const wrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}>{children}</TestProviders>

function FileControls({ rows, selected = [] }: { rows: string[]; selected?: string[] }) {
  return <FileSnapshotRecovery serverId="alpha">
    {rows.map(path => <FileSnapshotActions key={path} serverId="alpha" path={path} />)}
    <FileBatchActions serverId="alpha" paths={selected} basePath="/" />
  </FileSnapshotRecovery>
}

it('shares one GET across file rows, selection changes, clearing and remounted pages without range POSTs', async () => {
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
  let checks = 0
  server.use(http.post('*/api/snapshots/targets/check', () => { checks++; return HttpResponse.json({ allowed: true }) }))
  const view = render(<TestProviders client={client}><StrictMode><FileControls rows={['/config', '/config2', '/world', '/alias']} /></StrictMode></TestProviders>)
  await waitFor(() => expect((screen.getByRole('button', { name: '为 /config2 创建快照' }) as HTMLButtonElement).disabled).toBe(false))
  expect((screen.getByRole('button', { name: '为 /config 创建快照' }) as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole('button', { name: '为 /alias 创建快照' }) as HTMLButtonElement).disabled).toBe(false)
  expect(reads).toEqual(['alpha'])
  await act(async () => { await vi.advanceTimersByTimeAsync(61000) })
  view.rerender(<TestProviders client={client}><StrictMode><FileControls rows={['/config', '/config2', '/world', '/alias']} selected={['/config2', '/alias']} /></StrictMode></TestProviders>)
  await waitFor(() => expect((screen.getByRole('button', { name: '创建快照' }) as HTMLButtonElement).disabled).toBe(false))
  view.rerender(<TestProviders client={client}><StrictMode><FileControls rows={['/world/private', '/next']} selected={['/world/private']} /></StrictMode></TestProviders>)
  expect((screen.getByRole('button', { name: '创建快照' }) as HTMLButtonElement).disabled).toBe(true)
  view.rerender(<TestProviders client={client}><StrictMode><FileControls rows={['/next']} /></StrictMode></TestProviders>)
  await waitFor(() => expect((screen.getByRole('button', { name: '为 /next 创建快照' }) as HTMLButtonElement).disabled).toBe(false))
  expect(reads).toEqual(['alpha'])
  expect(checks).toBe(0)
})

it('matches logical path segments and merges overlapping selected roots without expanding aliases', () => {
  expect(checkLogicalSnapshotPaths(['config2'], ['config']).allowed).toBe(true)
  expect(checkLogicalSnapshotPaths(['alias/save.dat'], ['world']).allowed).toBe(true)
  expect(checkLogicalSnapshotPaths(['world/save.dat'], ['alias']).allowed).toBe(true)
  expect(checkLogicalSnapshotPaths(['alias/save.dat'], ['alias']).allowed).toBe(false)
  expect(checkLogicalSnapshotPaths(['world', 'world/private', 'world', './world/'], ['world/private', 'world/private'])).toEqual({ allowed: true, reason: null, skipped_paths: ['world/private'], skipped_count: 1 })
  expect(checkLogicalSnapshotPaths(['.', '/'], ['config', 'world/private'])).toEqual({ allowed: true, reason: null, skipped_paths: ['config', 'world/private'], skipped_count: 2 })
  expect(checkLogicalSnapshotPaths(['allowed', 'config'], ['config'])).toEqual({ allowed: true, reason: null, skipped_paths: ['config'], skipped_count: 1 })
  expect(checkLogicalSnapshotPaths(['config/a', 'config/b'], ['config'])).toEqual({ allowed: false, reason: '所选范围均被快照规则忽略，没有可处理的内容', skipped_paths: ['config'], skipped_count: 1 })
})

it('checks world selections through the world-only POST without loading file rules', async () => {
  const posted: unknown[] = []
  server.use(http.post('*/api/snapshots/targets/check', async ({ request }) => { posted.push(await request.json()); return HttpResponse.json({ allowed: true, skipped_count: 1, skipped_paths: ['world/region/c.0.0.mcc'], reason: null }) }))
  const scope = { kind: 'world' as const, server_id: 'alpha', selection: { type: 'chunks' as const, region_dir_relpath: 'world/region', chunks: [[0, 0] as [number, number]] } }
  const view = renderHook(() => useSnapshotTarget(scope), { wrapper })
  await waitFor(() => expect(view.result.current.data?.allowed).toBe(true))
  expect(posted).toEqual([{ scope }])
  expect(reads).toEqual([])
})

it('refreshes once on reentry while remounting rows neither polls nor exposes a cached success after failure', async () => {
  let fail = false
  let release = deferred<void>()
  server.use(http.get('*/api/snapshots/targets/rules', async () => {
    reads.push('alpha')
    if (fail) { await release.promise; return HttpResponse.json({ detail: '规则不可用' }, { status: 503 }) }
    return HttpResponse.json({ server_id: 'alpha', server_generation: 1, ignored_paths: [], rules_version: 'v1' })
  }))
  const view = render(<TestProviders client={client}><FileControls rows={['/allowed']} /></TestProviders>)
  await waitFor(() => expect((screen.getByRole('button', { name: '为 /allowed 创建快照' }) as HTMLButtonElement).disabled).toBe(false))
  view.unmount()
  fail = true
  render(<TestProviders client={client}><FileControls rows={['/allowed']} /></TestProviders>)
  expect((screen.getByRole('button', { name: '为 /allowed 创建快照' }) as HTMLButtonElement).disabled).toBe(true)
  await waitFor(() => expect(reads).toHaveLength(2))
  await act(async () => { release.resolve() })
  await waitFor(() => expect(client.getQueryState(queryKeys.snapshots.rules('alpha'))?.status).toBe('error'))
  expect((screen.getByRole('button', { name: '为 /allowed 创建快照' }) as HTMLButtonElement).disabled).toBe(true)
  fail = false
  release = deferred<void>()
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.snapshots.rules('alpha') }) })
  await waitFor(() => expect((screen.getByRole('button', { name: '为 /allowed 创建快照' }) as HTMLButtonElement).disabled).toBe(false))
  expect(reads).toHaveLength(3)
})

it.each(['update', 'reset'] as const)('updates current file feedback after snapshot configuration %s', async action => {
  server.use(
    http.put('*/api/config/modules/snapshots', async ({ request }) => { const body = await request.json() as { config_data: { ignored_paths: string[] } }; rules = body.config_data.ignored_paths; return HttpResponse.json({ success: true, message: '配置已保存' }) }),
    http.post('*/api/config/modules/snapshots/reset', () => { rules = []; return HttpResponse.json({ success: true, message: '配置已重置' }) }),
  )
  function ConfigurationAction() {
    const update = useUpdateModuleConfig()
    const reset = useResetModuleConfig()
    return <button onClick={() => action === 'update' ? update.mutate({ moduleName: 'snapshots', configData: { ignored_paths: [] } }) : reset.mutate('snapshots')}>修改规则</button>
  }
  render(<TestProviders client={client}><FileControls rows={['/config']} /><ConfigurationAction /></TestProviders>)
  await waitFor(() => expect(client.getQueryState(queryKeys.snapshots.rules('alpha'))?.status).toBe('success'))
  expect((screen.getByRole('button', { name: '为 /config 创建快照' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '修改规则' }))
  await waitFor(() => expect((screen.getByRole('button', { name: '为 /config 创建快照' }) as HTMLButtonElement).disabled).toBe(false))
  expect(reads).toEqual(['alpha', 'alpha'])
})

it('refreshes resolved world-name rules after a synchronous server.properties write', async () => {
  server.use(http.post('*/api/servers/alpha/files/content', async ({ request }) => { expect(new URL(request.url).searchParams.get('path')).toBe('/server.properties'); expect(await request.json()).toEqual({ content: 'level-name=another\n' }); rules = ['another/private']; return HttpResponse.json({ message: '保存成功' }) }))
  function SaveProperties() {
    const write = useUpdateFile('alpha')
    return <button onClick={() => write.mutate({ path: '/server.properties', content: 'level-name=another\n' })}>保存世界名</button>
  }
  render(<TestProviders client={client}><FileControls rows={['/world/private', '/another/private']} /><SaveProperties /></TestProviders>)
  await waitFor(() => expect((screen.getByRole('button', { name: '为 /another/private 创建快照' }) as HTMLButtonElement).disabled).toBe(false))
  expect((screen.getByRole('button', { name: '为 /world/private 创建快照' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '保存世界名' }))
  await waitFor(() => expect((screen.getByRole('button', { name: '为 /world/private 创建快照' }) as HTMLButtonElement).disabled).toBe(false))
  expect((screen.getByRole('button', { name: '为 /another/private 创建快照' }) as HTMLButtonElement).disabled).toBe(true)
  expect(reads).toEqual(['alpha', 'alpha'])
})

it.each(['snapshot_restore', 'archive_extract', 'server_remove', 'server_create'])('refreshes rules after changed %s operations and ignores read-only archive hashing', async kind => {
  const feed = createOperationFeed()
  const operation = (id: string, operationKind: string): Operation => ({ operation_id: id, kind: operationKind, state: 'succeeded', data_changed: true, updated_at: '2026-10-07T00:00:00Z', ended_at: '2026-10-07T00:00:00Z', resources: [{ kind: 'files', server_id: 'alpha', generation: 1, path: 'server.properties' }] })
  server.use(feed.handler)
  const view = renderHook(() => { const owner = useSnapshotRules('alpha', true); const target = useSnapshotTarget(fileSnapshotScope('alpha', ['/config'])); return { owner, target } }, { wrapper })
  await waitFor(() => expect(view.result.current.target.data?.allowed).toBe(false))
  render(<TestProviders client={client}><OperationObserver sessionId="session" /></TestProviders>)
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('session'))).toBeTruthy())
  reads.length = 0
  feed.publish(operation('hash', 'archive_hash'))
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.operations.all }) })
  expect(reads).toEqual([])
  rules = []
  feed.publish(operation('changed', kind))
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.operations.all }) })
  await waitFor(() => expect(view.result.current.target.data?.allowed).toBe(true))
  expect(reads).toEqual(['alpha'])
})

it('rejects a rules response for a different server and keeps replacement generations blocked until confirmed', async () => {
  const release = deferred<void>()
  let replacement = false
  let wrongServer = true
  server.use(http.get('*/api/snapshots/targets/rules', async () => {
    reads.push('alpha')
    if (replacement) await release.promise
    return HttpResponse.json({ server_id: wrongServer ? 'beta' : 'alpha', server_generation: generation, ignored_paths: [], rules_version: 'v' + generation })
  }))
  const view = renderHook(() => { const owner = useSnapshotRules('alpha', true); const target = useSnapshotTarget(fileSnapshotScope('alpha', ['/allowed'])); return { owner, target } }, { wrapper })
  await waitFor(() => expect(view.result.current.target.isError).toBe(true))
  expect(view.result.current.target.data).toBeUndefined()
  wrongServer = false
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.snapshots.rules('alpha') }) })
  await waitFor(() => expect(view.result.current.target.data?.allowed).toBe(true))
  replacement = true
  generation = 2
  await act(async () => { client.setQueryData(queryKeys.serverInfos.detail('alpha'), { id: 'alpha', serverGeneration: 2 }) })
  await waitFor(() => expect(view.result.current.target.data).toBeUndefined())
  await waitFor(() => expect(view.result.current.owner.isFetching).toBe(true))
  await act(async () => { release.resolve() })
  await waitFor(() => expect(view.result.current.target.data?.allowed).toBe(true))
  expect(client.getQueryData<SnapshotTargetRules>(queryKeys.snapshots.rules('alpha'))?.server_generation).toBe(2)
})

it('keeps rules unusable until server details confirm the registered generation', async () => {
  let registered = false
  rules = []
  server.use(http.get('*/api/servers/alpha', () => HttpResponse.json({ id: 'alpha', name: 'Alpha', serverType: 'VANILLA', server_generation: registered ? 1 : null })))
  const view = renderHook(() => { const owner = useSnapshotRules('alpha', true); const target = useSnapshotTarget(fileSnapshotScope('alpha', ['/allowed'])); return { owner, target } }, { wrapper })
  await waitFor(() => expect(view.result.current.owner.isSuccess).toBe(true))
  expect(view.result.current.owner.checking).toBe(true)
  expect(view.result.current.target.data).toBeUndefined()
  registered = true
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.serverInfos.detail('alpha') }) })
  await waitFor(() => expect(view.result.current.target.data?.allowed).toBe(true))
  expect(reads).toEqual(['alpha'])
})
