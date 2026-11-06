import { afterEach, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { clearBrowserUploads, openArchiveUpload, openFileUpload, updateUpload, useUploadStore } from '../uploads'
import UploadTaskList from './UploadTaskList'

afterEach(() => { cleanup(); clearBrowserUploads() })

it('reopens an archive from its single progress heading without duplicate filename or origin rows', () => {
  const id = openArchiveUpload([new File(['archive'], 'world.zip')])
  updateUpload(id, { status: 'uploading', message: '上传 world.zip (1/1)', progress: 25 })
  useUploadStore.setState({ visibleId: null })
  render(<UploadTaskList />)
  const heading = screen.getByRole('button', { name: '查看上传：world.zip' })
  expect(heading.textContent).toBe('上传 world.zip (1/1)')
  expect(screen.queryByText('world.zip', { exact: true })).toBeNull()
  expect(screen.queryByText('压缩包管理')).toBeNull()
  expect(screen.getByText('25%')).toBeTruthy()
  fireEvent.click(heading)
  expect(useUploadStore.getState().visibleId).toBe(id)
})

it('keeps a terminal filename in its clickable heading and the original destination in its tooltip', () => {
  const id = openFileUpload('server-a', '/mods', [new File(['file'], 'mod.jar')])
  updateUpload(id, { status: 'complete', message: '上传完成', progress: 100 })
  useUploadStore.setState({ visibleId: null })
  render(<UploadTaskList />)
  const heading = screen.getByRole('button', { name: '查看上传：mod.jar' })
  expect(heading.textContent).toBe('上传完成 mod.jar')
  expect(heading.getAttribute('title')).toBe('server-a · /mods')
  expect(screen.queryByText('server-a · /mods')).toBeNull()
  fireEvent.click(heading)
  expect(useUploadStore.getState().visibleId).toBe(id)
})

it('identifies a later file in a batch without adding the first filename to the heading', () => {
  const id = openArchiveUpload([new File(['first'], 'first.zip'), new File(['second'], 'second.zip')])
  updateUpload(id, { status: 'verifying', message: '校验 second.zip', progress: 50 })
  render(<UploadTaskList />)
  expect(screen.getByRole('button', { name: '查看上传：first.zip' }).textContent).toBe('校验 second.zip')
})

it('uses filenames selected after opening the dialog when displaying a later batch item', () => {
  const id = openArchiveUpload()
  updateUpload(id, { status: 'verifying', title: 'first.zip', fileNames: ['first.zip', 'second.zip'], fileCount: 2, message: '校验 second.zip' })
  render(<UploadTaskList />)
  expect(screen.getByRole('button', { name: '查看上传：first.zip' }).textContent).toBe('校验 second.zip')
})

it('distinguishes a numeric filename from the ordinary-file batch counter', () => {
  const id = openFileUpload('server-a', '/', [new File(['file'], '1')])
  updateUpload(id, { status: 'uploading', message: '上传中（1/1）' })
  render(<UploadTaskList />)
  expect(screen.getByRole('button', { name: '查看上传：1' }).textContent).toBe('上传中（1/1） 1')
})
