import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useNavigate } from 'react-router'
import { api } from '@/shared/http/api'
import { createTestClient, httpResponse } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { useFileBrowser } from './useFileBrowser'

const original = api.defaults.adapter
let client: ReturnType<typeof createTestClient>
beforeEach(() => {
  client = createTestClient()
  api.defaults.adapter = vi.fn(async config => httpResponse(config, config.url?.endsWith('/files') ? { items: [] } : { name: '服务器', serverType: 'vanilla' }))
})
afterEach(() => { api.defaults.adapter = original; client.clear() })

function Selection({ serverId }: { serverId: string }) {
  const browser = useFileBrowser(serverId)
  const navigate = useNavigate()
  return <>
    <output>{browser.selectedFiles.join(',')}</output>
    <button onClick={() => browser.setSelectedFiles(['/a.txt', '/b.txt'])}>选择</button>
    <button onClick={() => browser.setCurrentPage(2)}>翻页</button>
    <button onClick={() => browser.handleSearchChange('draft')}>编辑搜索</button>
    <button onClick={() => browser.handleSearch('draft', false)}>执行搜索</button>
    <button onClick={() => navigate('?path=/plugins')}>其他目录</button>
    <button onClick={() => navigate(-1)}>后退</button>
  </>
}

it('retains selection on pagination and clears it on executed filtering, navigation and server changes', async () => {
  const view = render(<TestProviders client={client}><Selection serverId="alpha" /></TestProviders>)
  fireEvent.click(screen.getByText('选择'))
  fireEvent.click(screen.getByText('翻页'))
  fireEvent.click(screen.getByText('编辑搜索'))
  expect(screen.getByRole('status').textContent).toBe('/a.txt,/b.txt')
  fireEvent.click(screen.getByText('执行搜索'))
  await waitFor(() => expect(screen.getByRole('status').textContent).toBe(''))
  fireEvent.click(screen.getByText('选择'))
  fireEvent.click(screen.getByText('其他目录'))
  expect(screen.getByRole('status').textContent).toBe('')
  fireEvent.click(screen.getByText('后退'))
  await waitFor(() => expect(screen.getByRole('status').textContent).toBe(''))
  fireEvent.click(screen.getByText('选择'))
  view.rerender(<TestProviders client={client}><Selection serverId="beta" /></TestProviders>)
  expect(screen.getByRole('status').textContent).toBe('')
})
