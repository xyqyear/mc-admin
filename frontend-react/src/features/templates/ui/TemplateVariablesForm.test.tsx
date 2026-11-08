import { useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import type { VariableDefinition } from '@/features/templates/contracts'
import { templateDefaultValues, templateValuesValid } from '@/features/templates/variableValues'
import { convertToFormData } from '@/features/templates/ui/variableUtils'
import TemplateVariablesForm from './TemplateVariablesForm'
import VariableEditDialog from './VariableEditDialog'

const definitions: VariableDefinition[] = [
  { type: 'string', name: 'name', display_name: '服务器名称', default: 'alpha', pattern: '^[a-z]+$' },
  { type: 'int', name: 'count', display_name: '计数', default: 0, min_value: 0, max_value: 8 },
  { type: 'float', name: 'ratio', display_name: '比例', default: 1.5, min_value: 0, max_value: 2 },
  { type: 'enum', name: 'mode', display_name: '运行模式', options: ['safe', 'fast'], default: 'safe' },
  { type: 'bool', name: 'enabled', display_name: '启用测试', default: false },
]

it('renders typed values, preserves a read-only name and rejects empty or out-of-range numbers', () => {
  function Editor() {
    const [value, setValue] = useState(templateDefaultValues(definitions))
    return <><TemplateVariablesForm definitions={definitions} value={value} onChange={setValue} readOnlyName /><output aria-label="提交值">{JSON.stringify(value)}</output><button disabled={!templateValuesValid(definitions, value)}>保存</button></>
  }
  render(<Editor />)
  expect((screen.getByLabelText('服务器名称') as HTMLInputElement).readOnly).toBe(true)
  expect((screen.getByLabelText('计数') as HTMLInputElement).value).toBe('0')
  fireEvent.change(screen.getByLabelText('计数'), { target: { value: '' } })
  expect(screen.getByRole('button', { name: '保存' }).hasAttribute('disabled')).toBe(true)
  fireEvent.change(screen.getByLabelText('计数'), { target: { value: '9' } })
  expect(screen.getByText('不能大于 8')).toBeTruthy()
  fireEvent.change(screen.getByLabelText('计数'), { target: { value: '0' } })
  fireEvent.change(screen.getByLabelText('比例'), { target: { value: '2' } })
  fireEvent.click(screen.getByRole('checkbox', { name: '启用测试' }))
  fireEvent.click(screen.getByRole('checkbox', { name: '启用测试' }))
  expect(JSON.parse(screen.getByLabelText('提交值').textContent!)).toEqual({ name: 'alpha', count: 0, ratio: 2, mode: 'safe', enabled: false })
  expect(screen.getByRole('button', { name: '保存' }).hasAttribute('disabled')).toBe(false)
})

it('treats persisted null defaults as absent when authoring variable definitions', () => {
  expect(convertToFormData([{ type: 'string', name: 'text', display_name: '文本', default: null, pattern: null, description: null }])[0]).toMatchObject({ default: undefined, pattern: undefined, description: undefined })
})

it('retains an invalid enum default until corrected and submits the authored definition', async () => {
  const accept = vi.fn()
  render(<VariableEditDialog open mode="edit" initialData={{ type: 'enum', name: 'mode', display_name: '模式', options: ['safe', 'fast'], default: 'missing' }} onOk={accept} onCancel={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: '确定' }))
  expect(accept).not.toHaveBeenCalled()
  await screen.findByText('默认值无效：请选择一个有效选项')
  expect((screen.getByLabelText('默认值') as HTMLInputElement).value).toBe('missing')
  fireEvent.change(screen.getByLabelText('默认值'), { target: { value: 'fast' } })
  fireEvent.click(screen.getByRole('button', { name: '确定' }))
  await waitFor(() => expect(accept).toHaveBeenCalledWith({ type: 'enum', name: 'mode', display_name: '模式', options: ['safe', 'fast'], default: 'fast' }))
})

it('validates numeric bounds while allowing false and zero defaults', () => {
  const accept = vi.fn()
  const view = render(<VariableEditDialog open mode="add" initialData={{ type: 'int', name: 'limit', display_name: '上限', min_value: 5, max_value: 2, default: 0 }} onOk={accept} onCancel={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: '确定' }))
  expect(accept).not.toHaveBeenCalled()
  screen.getByText('最小值不能大于最大值')
  fireEvent.change(screen.getByLabelText('最小值'), { target: { value: '0' } })
  fireEvent.click(screen.getByRole('button', { name: '确定' }))
  expect(accept).toHaveBeenCalledWith(expect.objectContaining({ default: 0, min_value: 0, max_value: 2 }))
  view.unmount()
  render(<VariableEditDialog open mode="edit" initialData={{ type: 'bool', name: 'flag', display_name: '开关', default: false }} onOk={accept} onCancel={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: '确定' }))
  expect(accept).toHaveBeenLastCalledWith(expect.objectContaining({ type: 'bool', default: false }))
})
