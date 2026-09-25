import { act, render, renderHook, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { versionUpdates } from './config'
import VersionUpdateDialog from './VersionUpdateDialog'
import { useVersionCheck } from './useVersionCheck'

const bundledVersion = vi.hoisted(() => ({ value: '6.0.0-beta.1' }))

vi.mock('./config', async importOriginal => ({
  ...await importOriginal<typeof import('./config')>(),
  get currentVersion() { return bundledVersion.value },
}))

const releaseCount = versionUpdates.length

afterEach(() => {
  versionUpdates.splice(releaseCount)
  bundledVersion.value = '6.0.0-beta.1'
  localStorage.clear()
  vi.useRealTimers()
})

describe('version update notifications', () => {
  it('lists only newer releases in descending SemVer order, including the final release', () => {
    versionUpdates.push(
      { version: '6.0.0-beta.2', date: '2026-09-25', title: '第二个测试版', description: '' },
      { version: '6.0.0', date: '2026-09-25', title: '正式版', description: '' },
      { version: '6.0.0-beta.10', date: '2026-09-25', title: '第十个测试版', description: '' },
    )
    const props = { open: true, onClose: vi.fn(), onRemindLater: vi.fn(), fromVersion: '6.0.0-beta.1' }
    const view = render(<VersionUpdateDialog {...props} toVersion="6.0.0" />)
    expect(screen.getAllByRole('heading', { level: 5 }).map(heading => heading.textContent)).toEqual([
      '正式版', '第十个测试版', '第二个测试版',
    ])

    view.rerender(<VersionUpdateDialog {...props} toVersion="6.0.0-beta.2" />)
    expect(screen.getAllByRole('heading', { level: 5 }).map(heading => heading.textContent)).toEqual(['第二个测试版'])
  })

  it('notifies an existing stable user about the prerelease and acknowledges that exact version', () => {
    vi.useFakeTimers()
    localStorage.setItem('mc-admin-last-seen-version', '5.3.0')
    const { result } = renderHook(useVersionCheck)
    act(() => vi.advanceTimersByTime(1000))
    expect(result.current).toMatchObject({ shouldShowDialog: true, fromVersion: '5.3.0', toVersion: '6.0.0-beta.1' })
    act(() => result.current.handleClose())
    expect(localStorage.getItem('mc-admin-last-seen-version')).toBe('6.0.0-beta.1')
    expect(result.current.shouldShowDialog).toBe(false)
  })

  it.each(['6.0.0-beta.1', '6.0.0-beta.2', '6.0.0'])('does not announce a new version to someone who already saw %s', version => {
    vi.useFakeTimers()
    localStorage.setItem('mc-admin-last-seen-version', version)
    const { result } = renderHook(useVersionCheck)
    act(() => vi.advanceTimersByTime(1000))
    expect(result.current.shouldShowDialog).toBe(false)
    expect(localStorage.getItem('mc-admin-last-seen-version')).toBe(version)
  })

  it.each([
    ['6.0.0-beta.1', '6.0.0-beta.2'],
    ['6.0.0-beta.2', '6.0.0'],
  ])('notifies a user upgrading from %s to %s', (previous, current) => {
    vi.useFakeTimers()
    bundledVersion.value = current
    localStorage.setItem('mc-admin-last-seen-version', previous)
    const { result } = renderHook(useVersionCheck)
    act(() => vi.advanceTimersByTime(1000))
    expect(result.current).toMatchObject({ shouldShowDialog: true, fromVersion: previous, toVersion: current })
  })
})
