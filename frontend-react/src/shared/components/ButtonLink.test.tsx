import { createRef } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router'
import { Tooltip, TooltipProvider, TooltipTrigger } from '@/shared/ui/tooltip'
import { ButtonLink } from './ButtonLink'

it('keeps styled tooltip navigation an anchor and follows ordinary clicks', () => {
  const ref = createRef<HTMLAnchorElement>()
  render(<MemoryRouter initialEntries={['/overview']}>
    <TooltipProvider><Tooltip><TooltipTrigger render={<ButtonLink ref={ref} to="/templates/new" variant="outline" size="sm" />}>
      创建模板
    </TooltipTrigger></Tooltip></TooltipProvider>
    <Routes>
      <Route path="/overview" element={<p>总览页面</p>} />
      <Route path="/templates/new" element={<p>创建模板页面</p>} />
    </Routes>
  </MemoryRouter>)

  const link = screen.getByRole('link', { name: '创建模板' })
  expect(link.tagName).toBe('A')
  expect(link.getAttribute('href')).toBe('/templates/new')
  expect(link.getAttribute('role')).toBeNull()
  expect(ref.current).toBe(link)
  expect(screen.queryByRole('button', { name: '创建模板' })).toBeNull()
  fireEvent.click(link)
  expect(screen.getByText('创建模板页面')).not.toBeNull()
})

it('preserves native new-tab attributes on a styled link', () => {
  render(<MemoryRouter><ButtonLink to="/archives" target="_blank" rel="noopener noreferrer">归档</ButtonLink></MemoryRouter>)
  const link = screen.getByRole('link', { name: '归档' })
  expect(link.getAttribute('href')).toBe('/archives')
  expect(link.getAttribute('target')).toBe('_blank')
  expect(link.getAttribute('rel')).toBe('noopener noreferrer')
  expect(link.getAttribute('role')).toBeNull()
})
