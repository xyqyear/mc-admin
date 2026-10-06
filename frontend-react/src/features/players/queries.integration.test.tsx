import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { usePlayerMapProfile, usePlayerMapProfiles } from '@/features/players/queries'
import type { PlayerMapProfileResponse } from '@/features/players/contracts'
import { queryKeys } from '@/shared/http/api'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { deferred } from '@/test/http'

const uuid = '0123456789abcdef0123456789abcdef'
const profile = (name: string): PlayerMapProfileResponse => ({ uuid, player_db_id: 1, current_name: name, avatar_base64: null, resolved: true, last_skin_update: null })
const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers() })

it('preserves map layers on unrelated renders while observing profile and UUID changes', async () => {
  client.setQueryData(queryKeys.players.mapProfileByUUID(uuid), profile('旧名字'))
  const { result, rerender } = renderHook(({ uuids }) => usePlayerMapProfiles(uuids, false), {
    initialProps: { uuids: [uuid] },
    wrapper: ({ children }) => <TestProviders client={client}>{children}</TestProviders>,
  })
  expect(result.current.profilesByUuid.get(uuid)?.current_name).toBe('旧名字')
  const initialProfiles = result.current.profilesByUuid
  act(() => { client.setQueryData(queryKeys.players.mapProfileByUUID(uuid), profile('新名字')) })
  await waitFor(() => expect(result.current.profilesByUuid.get(uuid)?.current_name).toBe('新名字'))
  const updatedProfiles = result.current.profilesByUuid
  expect(updatedProfiles).not.toBe(initialProfiles)
  rerender({ uuids: [uuid.toUpperCase(), uuid] })
  expect(result.current.profilesByUuid).toBe(updatedProfiles)
  rerender({ uuids: [uuid] })
  expect(result.current.profilesByUuid).toBe(updatedProfiles)

  rerender({ uuids: [] })
  expect(result.current.profilesByUuid.size).toBe(0)
  const emptyProfiles = result.current.profilesByUuid
  rerender({ uuids: [] })
  expect(result.current.profilesByUuid).toBe(emptyProfiles)
})

it('streams profiles into the shared cache without refetching a parallel profile observer', async () => {
  client.setQueryData(queryKeys.players.mapProfileByUUID(uuid), profile('旧名字'))
  server.use(http.post('*/api/players/profiles/stream', async ({ request }) => {
    expect(await request.json()).toEqual({ uuids: [uuid] })
    return new HttpResponse(`data: ${JSON.stringify({ event_type: 'profile', profile: profile('流更新') })}\n\ndata: ${JSON.stringify({ event_type: 'complete', total: 1, resolved: 1 })}\n\n`, { headers: { 'Content-Type': 'text/event-stream' } })
  }))
  const { result } = renderHook(() => ({ map: usePlayerMapProfiles([uuid, uuid.toUpperCase()]), single: usePlayerMapProfile(uuid) }), { wrapper: ({ children }) => <TestProviders client={client}>{children}</TestProviders> })
  await waitFor(() => expect(result.current.map.profilesByUuid.get(uuid)?.current_name).toBe('流更新'))
  expect(result.current.single.data?.current_name).toBe('流更新')
  expect(result.current.map.isFetching).toBe(false)
})

it.each([
  { label: 'a missing profile', events: [{ event_type: 'profile' }], message: '玩家资料格式无效，请重试' },
  { label: 'an invalid profile field', events: [{ event_type: 'profile', profile: { ...profile('无效资料'), resolved: 'yes' } }], message: '玩家资料格式无效，请重试' },
  { label: 'an incomplete finite stream', events: [{ event_type: 'profile', profile: profile('部分更新') }], message: '玩家资料连接已中断，请重试' },
  { label: 'an error terminal', events: [{ event_type: 'error', message: '资料服务不可用' }], message: '资料服务不可用' },
])('shows $label and preserves the cached profile until an explicit retry completes', async ({ events, message }) => {
  client.setQueryData(queryKeys.players.mapProfileByUUID(uuid), profile('缓存名字'))
  let attempts = 0
  server.use(http.post('*/api/players/profiles/stream', () => {
    attempts++
    const batch = attempts === 1 ? events : [{ event_type: 'unknown_future' }, { event_type: 'profile', profile: profile('重试成功') }, { event_type: 'complete', total: 1, resolved: 1 }]
    return new HttpResponse(batch.map(event => `data: ${JSON.stringify(event)}\n\n`).join(''), { headers: { 'Content-Type': 'text/event-stream' } })
  }))
  const { result } = renderHook(() => usePlayerMapProfiles([uuid]), { wrapper: ({ children }) => <TestProviders client={client}>{children}</TestProviders> })
  await waitFor(() => expect(result.current.error).toBe(message))
  expect(result.current.isFetching).toBe(false)
  expect(result.current.profilesByUuid.get(uuid)?.current_name).toBe(message === '玩家资料连接已中断，请重试' ? '部分更新' : '缓存名字')
  act(() => result.current.retry())
  await waitFor(() => expect(result.current.profilesByUuid.get(uuid)?.current_name).toBe('重试成功'))
  expect(attempts).toBe(2)
  expect(result.current.error).toBeNull()
})

it.each(['disable', 'unmount'])('does not request disabled profiles and aborts a pending request on %s without a visible failure', async (close) => {
  const started = deferred<void>()
  const aborted = deferred<void>()
  let attempts = 0
  server.use(http.post('*/api/players/profiles/stream', async ({ request }) => {
    attempts++
    request.signal.addEventListener('abort', () => aborted.resolve(), { once: true })
    started.resolve()
    await aborted.promise
    return new HttpResponse('')
  }))
  const { result, rerender, unmount } = renderHook(({ enabled }) => usePlayerMapProfiles([uuid], enabled), { initialProps: { enabled: false }, wrapper: ({ children }) => <TestProviders client={client}>{children}</TestProviders> })
  expect(attempts).toBe(0)
  rerender({ enabled: true })
  await started.promise
  if (close === 'disable') rerender({ enabled: false })
  else unmount()
  await aborted.promise
  expect(result.current.error).toBeNull()
  if (close === 'disable') {
    expect(result.current.isFetching).toBe(false)
    unmount()
  }
})
