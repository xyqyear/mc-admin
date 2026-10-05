import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router'

import ServerOperationButtons from '@/features/servers/ui/ServerOperationButtons'

const maintenance = vi.hoisted(() => ({ active: false }))
vi.mock('@/features/servers/queries', () => ({
  useServerQueries: () => ({ useServerMaintenance: () => ({ data: maintenance }) }),
}))
vi.mock('@/features/servers/commands', () => ({
  useServerMutations: () => ({ useServerOperation: () => ({ isPending: false, mutate: vi.fn() }) }),
}))
vi.mock('@/features/servers/ui/ServerOperationConfirmDialog', () => ({
  useServerOperationConfirm: () => ({ showConfirm: vi.fn(), confirmDialog: null }),
}))

it('keeps startup unavailable during local apply and server maintenance', () => {
  const view = (active = false) => <MemoryRouter>
    <ServerOperationButtons serverId="server" serverName="服务器" status="CREATED" maintenanceActive={active} />
  </MemoryRouter>
  const { rerender } = render(view(true))
  expect(screen.getByRole('button', { name: '启动' }).hasAttribute('disabled')).toBe(true)
  maintenance.active = true
  rerender(view())
  expect(screen.getByRole('button', { name: '启动' }).hasAttribute('disabled')).toBe(true)
  maintenance.active = false
  rerender(view())
  expect(screen.getByRole('button', { name: '启动' }).hasAttribute('disabled')).toBe(false)
})

it('restores blocking and displays the active task reason after a page remount', () => {
  const buttons = (status: 'EXISTS' | 'HEALTHY') => <MemoryRouter><ServerOperationButtons serverId="server" serverName="服务器" status={status} /></MemoryRouter>
  Object.assign(maintenance, { active: true, task_id: 'startup', description: '正在准备镜像和容器' })
  const view = render(buttons('EXISTS'))
  expect(screen.getByText('正在准备镜像和容器')).toBeTruthy()
  expect(screen.getByRole('button', { name: '查看任务' })).toBeTruthy()
  for (const name of ['启动', '停止', '重启', '下线']) expect(screen.getByRole('button', { name }).hasAttribute('disabled')).toBe(true)
  Object.assign(maintenance, { active: false, task_id: undefined, description: undefined })
  view.rerender(buttons('HEALTHY'))
  for (const name of ['停止', '重启', '下线']) expect(screen.getByRole('button', { name }).hasAttribute('disabled')).toBe(false)
  Object.assign(maintenance, { active: true, task_id: 'startup', description: '正在准备镜像和容器' })
  view.rerender(buttons('HEALTHY'))
  for (const name of ['停止', '重启', '下线']) expect(screen.getByRole('button', { name }).hasAttribute('disabled')).toBe(true)
  Object.assign(maintenance, { active: false, task_id: undefined, description: undefined })
  view.rerender(buttons('HEALTHY'))
  for (const name of ['停止', '重启', '下线']) expect(screen.getByRole('button', { name }).hasAttribute('disabled')).toBe(false)
  view.unmount()
})
