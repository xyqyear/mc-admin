import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router'

import ServerOperationButtons from './ServerOperationButtons'

const maintenance = vi.hoisted(() => ({ active: false }))
vi.mock('@/hooks/queries/base/useServerQueries', () => ({
  useServerQueries: () => ({ useServerMaintenance: () => ({ data: maintenance }) }),
}))
vi.mock('@/hooks/mutations/useServerMutations', () => ({
  useServerMutations: () => ({ useServerOperation: () => ({ isPending: false, mutate: vi.fn() }) }),
}))
vi.mock('@/components/dialogs/ServerOperationConfirmDialog', () => ({
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
