import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import bundledUpdates from '../../../public/static/release.json'
import { parseReleaseData, releaseDataOptions, useReleaseData } from './releaseData'
import VersionUpdateDialog from './VersionUpdateDialog'
import { useVersionCheck } from './useVersionCheck'

const clients: QueryClient[] = []
const entry = (version: string, title = version) => ({ version, date: '2026-10-31', title, description: '' })

function provider(data?: unknown) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  if (data) client.setQueryData(releaseDataOptions.queryKey, parseReleaseData(data))
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

afterEach(() => {
  clients.splice(0).forEach(client => client.clear())
  localStorage.clear()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('version update notifications', () => {
  it('validates the shipped release data', () => {
    expect(parseReleaseData(bundledUpdates).versionUpdates).toEqual(bundledUpdates)
  })

  it('lists only newer releases in descending SemVer order, including the final release', () => {
    const wrapper = provider([
      entry('6.0.0-beta.1', '首个测试版'), entry('6.0.0-beta.2', '第二个测试版'),
      entry('6.0.0', '正式版'), entry('6.0.0-beta.10', '第十个测试版'), entry('7.0.0', '后续版本'),
    ])
    const props = { open: true, onClose: vi.fn(), onRemindLater: vi.fn(), fromVersion: '6.0.0-beta.1' }
    const view = render(<VersionUpdateDialog {...props} toVersion="6.0.0" />, { wrapper })
    expect(screen.getAllByRole('heading', { level: 5 }).map(heading => heading.textContent)).toEqual(['正式版', '第十个测试版', '第二个测试版'])
    view.rerender(<VersionUpdateDialog {...props} toVersion="6.0.0-beta.2" />)
    expect(screen.getAllByRole('heading', { level: 5 }).map(heading => heading.textContent)).toEqual(['第二个测试版'])
  })

  it('shows the shipped final release notes when upgrading from beta.1', () => {
    render(<VersionUpdateDialog open onClose={vi.fn()} onRemindLater={vi.fn()}
      fromVersion="6.0.0-beta.1" toVersion="6.0.0" />, { wrapper: provider(bundledUpdates) })
    expect(screen.getAllByRole('heading', { level: 5 }).map(heading => heading.textContent)).toEqual(['文件批量操作与恢复升级'])
  })

  it('acknowledges exactly the displayed prerelease', () => {
    vi.useFakeTimers()
    localStorage.setItem('mc-admin-last-seen-version', '5.3.0')
    const { result } = renderHook(useVersionCheck, { wrapper: provider([entry('6.0.0-beta.1')]) })
    act(() => vi.advanceTimersByTime(1000))
    expect(result.current).toMatchObject({ shouldShowDialog: true, fromVersion: '5.3.0', toVersion: '6.0.0-beta.1' })
    act(() => result.current.handleClose())
    expect(localStorage.getItem('mc-admin-last-seen-version')).toBe('6.0.0-beta.1')
    expect(result.current.shouldShowDialog).toBe(false)
  })

  it.each(['6.0.0-beta.1', '6.0.0-beta.2', '6.0.0'])('does not announce a version already seen as %s', version => {
    vi.useFakeTimers()
    localStorage.setItem('mc-admin-last-seen-version', version)
    const { result } = renderHook(useVersionCheck, { wrapper: provider([entry('6.0.0-beta.1')]) })
    act(() => vi.advanceTimersByTime(1000))
    expect(result.current.shouldShowDialog).toBe(false)
    expect(localStorage.getItem('mc-admin-last-seen-version')).toBe(version)
  })

  it.each([['6.0.0-beta.1', '6.0.0-beta.2'], ['6.0.0-beta.2', '6.0.0']])('notifies an upgrade from %s to %s', (previous, current) => {
    vi.useFakeTimers()
    localStorage.setItem('mc-admin-last-seen-version', previous)
    const { result } = renderHook(useVersionCheck, { wrapper: provider([entry(current)]) })
    act(() => vi.advanceTimersByTime(1000))
    expect(result.current).toMatchObject({ shouldShowDialog: true, fromVersion: previous, toVersion: current })
  })

  it('records the first visit silently and preserves the one-hour snooze', () => {
    vi.useFakeTimers()
    const wrapper = provider([entry('7.0.0')])
    const first = renderHook(useVersionCheck, { wrapper })
    act(() => vi.advanceTimersByTime(1000))
    expect(first.result.current.shouldShowDialog).toBe(false)
    expect(localStorage.getItem('mc-admin-last-seen-version')).toBe('7.0.0')
    first.unmount()
    localStorage.setItem('mc-admin-last-seen-version', '6.0.0')
    const upgrade = renderHook(useVersionCheck, { wrapper })
    act(() => vi.advanceTimersByTime(1000))
    act(() => upgrade.result.current.handleRemindLater())
    expect(localStorage.getItem('mc-admin-last-seen-version')).toBe('6.0.0')
    upgrade.unmount()
    const snoozed = renderHook(useVersionCheck, { wrapper })
    act(() => vi.advanceTimersByTime(1000))
    expect(snoozed.result.current.shouldShowDialog).toBe(false)
    snoozed.unmount()
    act(() => vi.advanceTimersByTime(3_600_000))
    const expired = renderHook(useVersionCheck, { wrapper })
    act(() => vi.advanceTimersByTime(1000))
    expect(expired.result.current.shouldShowDialog).toBe(true)
  })

  it('does not acknowledge unavailable data and retries without a stale HTTP cache', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response('', { status: 503 }))
      .mockImplementation(() => Promise.resolve(new Response(JSON.stringify([entry('7.0.0', '新版本')]))))
    vi.stubGlobal('fetch', fetcher)
    localStorage.setItem('mc-admin-last-seen-version', '6.0.0')
    const wrapper = provider()
    const { result } = renderHook(useVersionCheck, { wrapper })
    render(<VersionUpdateDialog open fromVersion="6.0.0" toVersion="7.0.0"
      onClose={() => result.current.handleClose()} onRemindLater={vi.fn()} />, { wrapper })
    await screen.findByRole('alert')
    act(() => result.current.handleClose())
    expect(localStorage.getItem('mc-admin-last-seen-version')).toBe('6.0.0')
    expect(screen.getByRole('button', { name: '明白了' }).hasAttribute('disabled')).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await screen.findByRole('heading', { level: 5, name: '新版本' })
    expect(fetcher.mock.calls.every(([, options]) => options.cache === 'no-store')).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: '明白了' }))
    expect(localStorage.getItem('mc-admin-last-seen-version')).toBe('7.0.0')
  })

  it('rejects malformed deployed data instead of recording a version', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify([{ ...entry('7.0.0'), features: 'invalid' }])))))
    const { result } = renderHook(useReleaseData, { wrapper: provider() })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error?.message).toBe('版本信息格式错误')
    expect(localStorage.getItem('mc-admin-last-seen-version')).toBeNull()
  })

  it.each([[], [entry('7.0.0'), entry('7.0.0')], [entry('7.00.0')], [{ ...entry('7.0.0'), date: '2026-02-30' }]].map(data => ({ data })))('rejects invalid release entries $data', ({ data }) => {
    expect(() => parseReleaseData(data)).toThrow()
  })
})
