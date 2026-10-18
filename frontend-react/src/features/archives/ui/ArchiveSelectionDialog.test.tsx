import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router'
import { queryKeys } from '@/shared/http/api'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import ArchiveSelectionDialog from './ArchiveSelectionDialog'

const client = createTestClient()
afterEach(() => client.clear())

it('retains the chosen archive on native alternate clicks and closes on ordinary navigation', async () => {
  client.setQueryData(queryKeys.archive.files('/'), {
    current_path: '/',
    items: [{ name: 'backup.zip', path: '/backup.zip', type: 'file', size: 12, modified_at: 1 }],
  })
  const close = vi.fn()
  const select = vi.fn()
  render(<TestProviders client={client} route="/server/new"><Routes>
    <Route path="/server/new" element={<ArchiveSelectionDialog open onCancel={close} onSelect={select} />} />
    <Route path="/archives" element={<p>归档页面</p>} />
  </Routes></TestProviders>)

  fireEvent.click(await screen.findByText('backup.zip'))
  const selected = screen.getByRole('radio')
  const confirm = screen.getByRole('button', { name: '选择文件' }) as HTMLButtonElement
  expect(selected.getAttribute('aria-checked')).toBe('true')
  expect(confirm.disabled).toBe(false)
  const link = screen.getByRole('link', { name: '压缩包管理' })
  expect(link.getAttribute('href')).toBe('/archives')
  for (const input of [{ ctrlKey: true }, { metaKey: true }, { button: 1 }]) {
    window.addEventListener('click', (event) => event.preventDefault(), { once: true })
    fireEvent.click(link, input)
    expect(selected.getAttribute('aria-checked')).toBe('true')
    expect(confirm.disabled).toBe(false)
    expect(screen.getByRole('dialog')).not.toBeNull()
  }
  expect(close).not.toHaveBeenCalled()
  expect(select).not.toHaveBeenCalled()
  fireEvent.click(link)
  expect(close).toHaveBeenCalledTimes(1)
  expect(select).not.toHaveBeenCalled()
  expect(screen.getByText('归档页面')).not.toBeNull()
})
