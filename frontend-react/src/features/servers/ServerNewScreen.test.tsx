import { StrictMode } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { queryKeys } from '@/shared/http/api'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import ServerNewScreen from './ServerNewScreen'

vi.mock('@/features/servers/ui/ServerNew/index', () => ({
  TraditionalCreationMode: () => null,
  TemplateCreationMode: ({ setSelectedTemplateId, templateFormData, setTemplateFormData }: {
    setSelectedTemplateId: (id: number) => void
    templateFormData: Record<string, unknown>
    setTemplateFormData: (value: Record<string, unknown>) => void
  }) => <>
    <button onClick={() => setSelectedTemplateId(1)}>模板一</button>
    <button onClick={() => setSelectedTemplateId(2)}>模板二</button>
    <input aria-label="服务器名称" value={String(templateFormData.name ?? '')} onChange={event => setTemplateFormData({ ...templateFormData, name: event.target.value })} />
    <output aria-label="游戏端口">{String(templateFormData.game_port ?? '')}</output>
  </>,
}))
vi.mock('@/features/archives/ui/ArchiveSelectionDialog', () => ({ default: () => null }))
const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

it('preserves authored values through port refresh and initializes a newly selected template', async () => {
  const client = createTestClient()
  let suggestedPort = 25565
  server.use(
    http.get('*/api/tasks', () => HttpResponse.json({ tasks: [], total: 0 })),
    http.get('*/api/templates/ports/available', () => HttpResponse.json({ suggested_game_port: suggestedPort, suggested_rcon_port: 25575 })),
    http.get('*/api/templates/:id/schema', ({ params }) => HttpResponse.json({ json_schema: {
      type: 'object', properties: { name: { type: 'string', default: `server-${params.id}` }, game_port: { type: 'number' } },
    } })),
  )
  const view = render(<StrictMode><TestProviders client={client}><ServerNewScreen /></TestProviders></StrictMode>)
  fireEvent.click(screen.getByText('模板一'))
  const name = screen.getByRole('textbox', { name: '服务器名称' }) as HTMLInputElement
  await waitFor(() => expect(name.value).toBe('server-1'))
  await waitFor(() => expect(screen.getByLabelText('游戏端口').textContent).toBe('25565'))
  fireEvent.change(name, { target: { value: 'survival' } })
  suggestedPort = 25566
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.templates.availablePorts() }) })
  expect(name.value).toBe('survival')
  expect(screen.getByLabelText('游戏端口').textContent).toBe('25565')
  fireEvent.click(screen.getByText('模板二'))
  await waitFor(() => expect(name.value).toBe('server-2'))
  expect(screen.getByLabelText('游戏端口').textContent).toBe('25566')
  view.unmount()
  client.clear()
})
