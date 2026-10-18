import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useLocation, useNavigate } from 'react-router'
import { api } from '@/shared/http/api'
import { createTestClient, httpResponse } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { useFileBrowser } from './useFileBrowser'
import FileBreadcrumb from './components/FileBreadcrumb'
import FileToolbar from './components/FileToolbar'
import FileTable from './components/FileTable'
import { SnapshotRecoveryContext } from './snapshotRecoveryContext'

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

function DirectoryNavigation() {
  const browser = useFileBrowser('alpha')
  const location = useLocation()
  const navigate = useNavigate()
  const idle = () => undefined
  return <>
    <output aria-label="当前位置">{location.pathname + location.search}</output>
    <output aria-label="已选路径">{browser.selectedFiles.join(',')}</output>
    <button onClick={() => browser.setSelectedFiles(['/a.txt'])}>选择</button>
    <button onClick={() => navigate(-1)}>后退</button>
    <FileBreadcrumb currentPath={browser.currentPath} getPathHref={browser.getPathHref} onNavigateToPath={browser.handleNavigateToPath} />
    {browser.currentPath !== '/' && <FileToolbar
      currentPath={browser.currentPath}
      parentHref={browser.getPathHref(browser.parentPath)}
      serverId="alpha"
      isLoadingFiles={false}
      createArchiveMutation={{ isPending: false }}
      populateServerMutation={{ isPending: false }}
      restoreOwnershipMutation={{ isPending: false }}
      onNavigateToParent={browser.handleNavigateToParent}
      onRefresh={idle} onUpload={idle} onCreateFile={idle}
      onCompressServer={idle} onReplaceServerFiles={idle} onRestoreOwnership={idle}
    />}
    <SnapshotRecoveryContext.Provider value={{ busy: false, create: idle, restore: idle, history: idle }}>
      <FileTable
        fileData={{ items: [{ name: 'nested', path: '/配置 #&+/child/nested', type: 'directory', size: 0, modified_at: 0 }] }}
        isLoadingFiles={false}
        selectedFiles={browser.selectedFiles} setSelectedFiles={browser.setSelectedFiles}
        currentPage={browser.currentPage} pageSize={browser.pageSize}
        setCurrentPage={browser.setCurrentPage} setPageSize={browser.setPageSize}
        serverId="alpha" getPathHref={browser.getPathHref}
        onFolderOpen={browser.handleFolderOpen}
        onFileEdit={idle} onFileDelete={idle} onFileDownload={idle} onFileRename={idle} onFileCompress={idle}
        createArchiveMutation={{ isPending: false }}
      />
    </SnapshotRecoveryContext.Provider>
  </>
}

it.each([
  ['根目录', null],
  ['配置 #&+', '/配置 #&+'],
  ['返回上级', '/配置 #&+'],
  ['nested', '/配置 #&+/child/nested'],
])('opens %s natively without clearing source state and clears filters and selection on ordinary navigation', async (name, targetPath) => {
  const route = '/server/alpha/files?path=%2F%E9%85%8D%E7%BD%AE+%23%26%2B%2Fchild&q=config.*&regex=true&view=list'
  render(<TestProviders client={client} route={route}><DirectoryNavigation /></TestProviders>)
  fireEvent.click(screen.getByText('选择'))
  const link = screen.getByRole('link', { name })
  const url = new URL(link.getAttribute('href')!, 'https://example.test')
  expect(url.pathname).toBe('/server/alpha/files')
  expect(url.searchParams.get('path')).toBe(targetPath)
  expect(url.searchParams.get('view')).toBe('list')
  expect(url.searchParams.has('q')).toBe(false)
  expect(url.searchParams.has('regex')).toBe(false)
  expect(screen.getByRole('button', { name: '上传文件' })).toBeTruthy()
  for (const modifiers of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }]) {
    let preventedByComponent = false
    window.addEventListener('click', event => {
      preventedByComponent = event.defaultPrevented
      event.preventDefault()
    }, { once: true })
    fireEvent.click(link, modifiers)
    expect(preventedByComponent).toBe(false)
  }
  fireEvent(link, new MouseEvent('auxclick', { button: 1, bubbles: true, cancelable: true }))
  expect(screen.getByRole('status', { name: '当前位置' }).textContent).toBe(route)
  expect(screen.getByRole('status', { name: '已选路径' }).textContent).toBe('/a.txt')
  fireEvent.click(link)
  await waitFor(() => expect(screen.getByRole('status', { name: '当前位置' }).textContent).toBe(url.pathname + url.search))
  expect(screen.getByRole('status', { name: '已选路径' }).textContent).toBe('')
  fireEvent.click(screen.getByText('后退'))
  await waitFor(() => expect(screen.getByRole('status', { name: '当前位置' }).textContent).toBe(route))
})
