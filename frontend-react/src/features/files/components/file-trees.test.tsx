import { fireEvent, render, screen, within } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import FileUploadTree from './dialogs/FileUploadTree'
import FileSearchResultTree from './FileSearchResultTree'
import type { SearchFileItem } from '@/features/files/contracts'

it('keeps upload input order, full folder identities and first duplicate metadata while expanding manually', () => {
  const file = (path: string, content: string) => {
    const selected = new File([content], path.split('/').at(-1)!)
    Object.defineProperty(selected, 'webkitRelativePath', { value: path })
    return selected
  }
  render(<FileUploadTree files={[file('z/config.toml', 'first'), file('a/deep/config.toml', 'other'), file('z/config.toml', 'ignored duplicate')]} />)
  expect(screen.queryByText('config.toml')).toBeNull()
  expect(screen.getByText('z').compareDocumentPosition(screen.getByText('a')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '展开所有' }))
  const leaves = screen.getAllByText('config.toml')
  expect(leaves).toHaveLength(2)
  expect(within(leaves[0].parentElement!).getByText('(5 B)')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '收起所有' }))
  expect(screen.queryByText('config.toml')).toBeNull()
})

it('auto-expands search paths, preserves directory leaves and highlights, and selects full leading-slash keys', () => {
  const select = vi.fn()
  const entry = (path: string, type: SearchFileItem['type'], size = 1): SearchFileItem => ({ path, name: path.split('/').at(-1)!, type, size, modified_at: '2026-10-01T00:00:00Z' })
  const results = [entry('/config', 'directory'), entry('/config/nested/settings.toml', 'file', 5), entry('/other/settings.toml', 'file', 8)]
  const { rerender } = render(<FileSearchResultTree searchResults={results} currentRegex="settings" onSelect={select} />)
  expect(screen.getAllByText('settings', { selector: 'mark' })).toHaveLength(2)
  const config = screen.getByText('config')
  expect(config.parentElement!.querySelector('svg.lucide-folder')).toBeTruthy()
  fireEvent.click(config)
  expect(select).toHaveBeenLastCalledWith(['/config'])
  expect(screen.queryByText('nested')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '展开所有' }))
  fireEvent.click(screen.getAllByText('settings', { selector: 'mark' })[0])
  expect(select).toHaveBeenLastCalledWith(['/config/nested/settings.toml'])
  fireEvent.click(screen.getByRole('button', { name: '收起所有' }))
  expect(screen.queryByText('settings', { selector: 'mark' })).toBeNull()
  rerender(<FileSearchResultTree searchResults={results} currentRegex="toml" onSelect={select} />)
  expect(screen.getAllByText('toml', { selector: 'mark' })).toHaveLength(2)
})
