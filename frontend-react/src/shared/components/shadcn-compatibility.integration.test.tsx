import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { getCoreRowModel, getPaginationRowModel, useReactTable } from '@tanstack/react-table'
import { expect, it, vi } from 'vitest'
import { useConfirm } from '@/shared/hooks/useConfirm'
import { Button } from '@/shared/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from '@/shared/ui/dialog'
import { DataTable } from './DataTable'

function DeleteConfirmation({ onConfirm }: { onConfirm: () => void | Promise<void> }) {
  const { confirm, confirmDialog } = useConfirm()
  return <>
    <Button onClick={() => confirm({
      title: '删除文件',
      description: '确认后将删除选中的文件',
      confirmText: '删除',
      onConfirm,
    })}>删除选中文件</Button>
    {confirmDialog}
  </>
}

it('cancels a destructive confirmation without applying the operation', async () => {
  const onConfirm = vi.fn()
  render(<DeleteConfirmation onConfirm={onConfirm} />)
  fireEvent.click(screen.getByRole('button', { name: '删除选中文件' }))
  const dialog = await screen.findByRole('alertdialog', { name: '删除文件' })
  expect(within(dialog).getByText('确认后将删除选中的文件')).toBeTruthy()
  fireEvent.click(within(dialog).getByRole('button', { name: '取消' }))
  await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
  expect(onConfirm).not.toHaveBeenCalled()
})

it('keeps confirmation protected until the accepted operation completes', async () => {
  let finish: () => void = () => undefined
  const pending = new Promise<void>((resolve) => { finish = resolve })
  const onConfirm = vi.fn(() => pending)
  render(<DeleteConfirmation onConfirm={onConfirm} />)
  fireEvent.click(screen.getByRole('button', { name: '删除选中文件' }))
  const dialog = await screen.findByRole('alertdialog', { name: '删除文件' })
  const confirm = within(dialog).getByRole('button', { name: '删除' })
  const cancel = within(dialog).getByRole('button', { name: '取消' })
  fireEvent.click(confirm)
  expect(onConfirm).toHaveBeenCalledTimes(1)
  expect(confirm.hasAttribute('disabled')).toBe(true)
  expect(cancel.hasAttribute('disabled')).toBe(true)
  fireEvent.click(confirm)
  fireEvent.click(cancel)
  fireEvent.keyDown(dialog, { key: 'Escape', code: 'Escape' })
  expect(screen.getByRole('alertdialog', { name: '删除文件' })).toBeTruthy()
  expect(onConfirm).toHaveBeenCalledTimes(1)
  await act(async () => { finish(); await pending })
  await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
})

it('closes a file details dialog with Escape and returns focus to its trigger', async () => {
  render(<Dialog>
    <DialogTrigger render={<Button />}>查看文件详情</DialogTrigger>
    <DialogContent>
      <DialogTitle>文件详情</DialogTitle>
      <DialogDescription>查看选中文件的属性</DialogDescription>
      <input aria-label="文件备注" />
    </DialogContent>
  </Dialog>)
  const trigger = screen.getByRole('button', { name: '查看文件详情' })
  trigger.focus()
  fireEvent.click(trigger)
  const dialog = await screen.findByRole('dialog', { name: '文件详情' })
  await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))
  fireEvent.keyDown(document.activeElement!, { key: 'Escape', code: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  await waitFor(() => expect(document.activeElement).toBe(trigger))
})

const files = Array.from({ length: 25 }, (_, index) => ({ name: `文件${index + 1}` }))

function FileList() {
  const table = useReactTable({
    data: files,
    columns: [{ accessorKey: 'name', header: '文件名' }],
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageIndex: 0, pageSize: 10 } },
  })
  return <DataTable table={table} />
}

it('shows localized page sizes and updates the visible file range after selecting an option', async () => {
  render(<FileList />)
  const trigger = screen.getByRole('combobox')
  expect(trigger.textContent).toContain('10条/页')
  expect(screen.getByText('1-10 共 25 条')).toBeTruthy()
  expect(screen.queryByText('文件11')).toBeNull()
  fireEvent.click(trigger)
  const option = await screen.findByRole('option', { name: '20条/页' })
  fireEvent.pointerDown(option)
  fireEvent.click(option)
  await waitFor(() => expect(trigger.textContent).toContain('20条/页'))
  expect(screen.getByText('1-20 共 25 条')).toBeTruthy()
  expect(screen.getByText('文件20')).toBeTruthy()
  expect(screen.queryByText('文件21')).toBeNull()
  await waitFor(() => expect(screen.queryByRole('listbox')).toBeNull())
})
