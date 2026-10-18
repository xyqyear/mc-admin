import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import CompressionResultDialog from './CompressionResultDialog'

function SourceLocation() {
  return <p data-testid="location">{useLocation().pathname}</p>
}

it('follows the archive destination normally and retains download as an action', () => {
  const close = vi.fn()
  const download = vi.fn()
  render(<MemoryRouter initialEntries={['/files']}><Routes>
    <Route path="/files" element={<CompressionResultDialog open onCancel={close} archiveFilename="backup.zip" message="压缩完成" onDownload={download} downloadLoading={false} />} />
    <Route path="/archives" element={<p>归档页面</p>} />
  </Routes></MemoryRouter>)

  const link = screen.getByRole('link', { name: '压缩包管理' })
  expect(link.getAttribute('href')).toBe('/archives')
  fireEvent.click(screen.getByRole('button', { name: '立即下载' }))
  expect(download).toHaveBeenCalledTimes(1)
  expect(close).not.toHaveBeenCalled()
  fireEvent.click(link)
  expect(close).toHaveBeenCalledTimes(1)
  expect(screen.getByText('归档页面')).not.toBeNull()
})

it.each([
  { ctrlKey: true },
  { metaKey: true },
  { shiftKey: true },
  { altKey: true },
  { button: 1 },
])('keeps the source result dialog open for native alternate navigation: %j', (input) => {
  const close = vi.fn()
  const download = vi.fn()
  render(<MemoryRouter initialEntries={['/server/alpha/files']}><SourceLocation /><CompressionResultDialog open onCancel={close} archiveFilename="backup.zip" message="压缩完成" onDownload={download} downloadLoading={false} /></MemoryRouter>)

  const link = screen.getByRole('link', { name: '压缩包管理' })
  // JSDOM cannot open links; cancel its default after React handles the click.
  window.addEventListener('click', (event) => event.preventDefault(), { once: true })
  fireEvent.click(link, input)
  expect(close).not.toHaveBeenCalled()
  expect(download).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog')).not.toBeNull()
  expect(screen.getByTestId('location').textContent).toBe('/server/alpha/files')
  expect(link.getAttribute('href')).toBe('/archives')
})
