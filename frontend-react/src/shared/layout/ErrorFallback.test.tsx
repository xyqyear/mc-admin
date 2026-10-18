import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router'
import { ErrorFallback } from './ErrorFallback'

it('keeps retry as an action and returns home through document navigation', () => {
  const reset = vi.fn()
  render(<MemoryRouter initialEntries={['/broken']}><Routes>
    <Route path="/broken" element={<ErrorFallback error={null} resetErrorBoundary={reset} />} />
    <Route path="/" element={<p>首页 SPA 路由</p>} />
  </Routes></MemoryRouter>)

  expect(screen.getByText('出错了')).not.toBeNull()
  expect(screen.getByText('发生了意外错误')).not.toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '重试' }))
  expect(reset).toHaveBeenCalledTimes(1)
  const home = screen.getByRole('link', { name: '返回首页' })
  expect(home.getAttribute('href')).toBe('/')
  expect(home.getAttribute('role')).toBeNull()
  let preventedByApplication = false
  // JSDOM cannot reload the document; cancel its default after React handles the click.
  window.addEventListener('click', (event) => {
    preventedByApplication = event.defaultPrevented
    event.preventDefault()
  }, { once: true })
  fireEvent.click(home)
  expect(preventedByApplication).toBe(false)
  expect(screen.queryByText('首页 SPA 路由')).toBeNull()
  expect(screen.getByText('出错了')).not.toBeNull()
  expect(reset).toHaveBeenCalledTimes(1)
})
