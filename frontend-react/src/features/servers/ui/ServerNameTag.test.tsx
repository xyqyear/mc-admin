import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router'
import { ServerNameTag } from './ServerNameTag'

it('exposes the complete server destination without activating its parent action', () => {
  const selectRow = vi.fn()
  render(<MemoryRouter initialEntries={['/players']}>
    <div onClick={selectRow}><ServerNameTag serverId="alpha-server" maxLength={5} /></div>
    <Routes>
      <Route path="/players" element={<p>玩家列表</p>} />
      <Route path="/server/alpha-server" element={<p>服务器详情</p>} />
    </Routes>
  </MemoryRouter>)

  const link = screen.getByRole('link', { name: 'alpha...' })
  expect(link.getAttribute('href')).toBe('/server/alpha-server')
  expect(link.getAttribute('title')).toBe('alpha-server')
  expect(link.getAttribute('role')).toBeNull()
  fireEvent.click(link)
  expect(screen.getByText('服务器详情')).not.toBeNull()
  expect(selectRow).not.toHaveBeenCalled()
})
