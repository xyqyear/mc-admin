import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { useLocation } from 'react-router'
import { queryKeys } from '@/shared/http/api'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { OnlinePlayersCard } from './OnlinePlayersCard'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers() })

it('opens the selected player in place and retains the detail when the player goes offline', async () => {
  const uuid = '0123456789ab4def8123456789abcdef'
  const lookedUp: string[] = []
  server.use(
    http.get('*/api/servers/alpha/online-players', () => HttpResponse.json([{ player_db_id: 1, uuid, current_name: 'Alex', avatar_base64: null, joined_at: '2026-10-01T00:00:00Z', session_duration_seconds: 12 }])),
    http.get('*/api/players/uuid/:uuid', ({ params }) => {
      lookedUp.push(String(params.uuid))
      return HttpResponse.json({ player_db_id: 1, uuid, current_name: 'Alex', skin_base64: null, avatar_base64: null, is_online: true, current_servers: [], first_seen: '2026-10-01T00:00:00Z', last_seen: null, total_playtime_seconds: 12, total_sessions: 1, total_messages: 0, total_achievements: 0 })
    }),
    http.get('*/api/players/1/sessions/stats', () => HttpResponse.json({ total_sessions: 1, total_playtime_seconds: 12, average_session_seconds: 12, longest_session_seconds: 12, sessions_by_server: {}, playtime_by_server: {} })),
    http.get('*/api/players/1/:kind', () => HttpResponse.json([])),
  )
  function Overview({ healthy }: { healthy: boolean }) {
    return <><output aria-label="当前页面">{useLocation().pathname}</output><OnlinePlayersCard serverId="alpha" isHealthy={healthy} /></>
  }
  const view = render(<TestProviders client={client} route="/server/alpha"><Overview healthy /></TestProviders>)
  const card = await screen.findByRole('button', { name: '查看 Alex 的玩家详情' })
  card.focus()
  expect(document.activeElement).toBe(card)
  fireEvent.click(card)
  const dialog = await screen.findByRole('dialog', { name: /玩家详情/ })
  await within(dialog).findByText('Alex')
  expect(lookedUp).toEqual([uuid])
  expect(screen.getByLabelText('当前页面').textContent).toBe('/server/alpha')
  await act(async () => { client.setQueryData(queryKeys.players.serverOnline('alpha'), []) })
  view.rerender(<TestProviders client={client} route="/server/alpha"><Overview healthy={false} /></TestProviders>)
  expect(screen.queryByRole('button', { name: '查看 Alex 的玩家详情' })).toBeNull()
  expect(screen.getByRole('dialog', { name: /玩家详情/ })).toBeTruthy()
  fireEvent.keyDown(dialog, { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(screen.getByLabelText('当前页面').textContent).toBe('/server/alpha')
})
