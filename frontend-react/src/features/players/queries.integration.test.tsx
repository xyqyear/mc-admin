import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { usePlayerMapProfile, usePlayerMapProfiles } from '@/features/players/queries'
import type { PlayerMapProfileResponse } from '@/features/players/contracts'
import { queryKeys } from '@/shared/http/api'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'

const uuid = '0123456789abcdef0123456789abcdef'
const profile = (name: string): PlayerMapProfileResponse => ({ uuid, player_db_id: 1, current_name: name, avatar_base64: null, resolved: true, last_skin_update: null })
const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers() })

it('uses one profile cache when the map is disabled and another observer changes the name', async () => {
  client.setQueryData(queryKeys.players.mapProfileByUUID(uuid), profile('旧名字'))
  const { result } = renderHook(() => usePlayerMapProfiles([uuid], false), { wrapper: ({ children }) => <TestProviders client={client}>{children}</TestProviders> })
  expect(result.current.profilesByUuid.get(uuid)?.current_name).toBe('旧名字')
  act(() => { client.setQueryData(queryKeys.players.mapProfileByUUID(uuid), profile('新名字')) })
  await waitFor(() => expect(result.current.profilesByUuid.get(uuid)?.current_name).toBe('新名字'))
})

it('preserves map layers on unrelated renders while observing profile and UUID changes', async () => {
  client.setQueryData(queryKeys.players.mapProfileByUUID(uuid), profile('旧名字'))
  const { result, rerender } = renderHook(({ uuids }) => usePlayerMapProfiles(uuids, false), {
    initialProps: { uuids: [uuid] },
    wrapper: ({ children }) => <TestProviders client={client}>{children}</TestProviders>,
  })
  const initialProfiles = result.current.profilesByUuid
  rerender({ uuids: [uuid.toUpperCase(), uuid] })
  expect(result.current.profilesByUuid).toBe(initialProfiles)

  act(() => { client.setQueryData(queryKeys.players.mapProfileByUUID(uuid), profile('新名字')) })
  await waitFor(() => expect(result.current.profilesByUuid.get(uuid)?.current_name).toBe('新名字'))
  const updatedProfiles = result.current.profilesByUuid
  expect(updatedProfiles).not.toBe(initialProfiles)
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
