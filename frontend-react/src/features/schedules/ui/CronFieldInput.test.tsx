import { useState } from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { expect, it } from 'vitest'
import CronFieldInput from './CronFieldInput'

function Field({ initialValue, min = 0, disabled = false }: { initialValue: string; min?: number; disabled?: boolean }) {
  const [value, setValue] = useState(initialValue)
  return <>
    <CronFieldInput value={value} onChange={setValue} config={{ label: '分钟', min, max: 59 }} disabled={disabled} />
    <output aria-label="已接受表达式">{value}</output>
  </>
}

async function selectMode(name: string) {
  fireEvent.click(screen.getAllByRole('combobox')[0])
  const option = await screen.findByRole('option', { name })
  fireEvent.pointerDown(option)
  fireEvent.click(option)
}

it('sends zero to the controlled parent for a specific value and a range endpoint', () => {
  const { rerender } = render(<Field initialValue="5" />)
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '0' } })
  expect(screen.getByLabelText('已接受表达式').textContent).toBe('0')
  rerender(<Field key="range" initialValue="5-15" />)
  fireEvent.change(screen.getAllByRole('spinbutton')[0], { target: { value: '0' } })
  expect(screen.getByLabelText('已接受表达式').textContent).toBe('0-15')
})

it('sends an explicitly cleared raw field and allows editing it again', () => {
  render(<Field initialValue="?" />)
  fireEvent.change(screen.getByRole('textbox'), { target: { value: '' } })
  expect(screen.getByLabelText('已接受表达式').textContent).toBe('')
  fireEvent.change(screen.getByRole('textbox'), { target: { value: '?' } })
  expect(screen.getByLabelText('已接受表达式').textContent).toBe('?')
})

it('sends the minimum interval start without recovering the previous start', async () => {
  render(<Field initialValue="5/10" />)
  fireEvent.click(screen.getAllByRole('combobox')[1])
  const option = await screen.findByRole('option', { name: '任意' })
  fireEvent.pointerDown(option)
  fireEvent.click(option)
  await waitFor(() => expect(screen.getByLabelText('已接受表达式').textContent).toBe('*/10'))
})

it.each([
  ['5', '指定值'], ['5-15', '范围'], ['5/10', '间隔'], ['1,3', '列表'], ['?', '自定义'],
])('restores the %s draft when changing modes without new parameters', async (draft, mode) => {
  render(<Field initialValue={draft} />)
  fireEvent.click(screen.getAllByRole('combobox')[0])
  const anyOption = await screen.findByRole('option', { name: '任意值 (*)' })
  fireEvent.pointerDown(anyOption)
  fireEvent.click(anyOption)
  await waitFor(() => expect(screen.getByLabelText('已接受表达式').textContent).toBe('*'))
  fireEvent.click(screen.getByRole('combobox'))
  const specificOption = await screen.findByRole('option', { name: mode })
  fireEvent.pointerDown(specificOption)
  fireEvent.click(specificOption)
  await waitFor(() => expect(screen.getByLabelText('已接受表达式').textContent).toBe(draft))
})

it('keeps controls disabled without changing the accepted draft', () => {
  render(<Field initialValue="5" disabled />)
  expect(screen.getByRole('spinbutton').hasAttribute('disabled')).toBe(true)
  expect(screen.getByRole('combobox').hasAttribute('disabled')).toBe(true)
  expect(screen.getByLabelText('已接受表达式').textContent).toBe('5')
})

it('shows external replacements without emitting edits and retains inactive mode drafts', async () => {
  function ControlledField() {
    const [value, setValue] = useState('5')
    const [edits, setEdits] = useState<string[]>([])
    return <>
      <CronFieldInput value={value} config={{ label: '分钟', min: 0, max: 59 }} onChange={next => { setValue(next); setEdits(previous => [...previous, next]) }} />
      <output aria-label="父级接受值">{value}</output>
      <output aria-label="用户修改记录">{edits.join(';')}</output>
      <button onClick={() => setValue('2-8')}>加载范围</button>
      <button onClick={() => setValue('4/9')}>加载间隔</button>
      <button onClick={() => setValue('3,7')}>加载列表</button>
      <button onClick={() => setValue('?')}>加载自定义</button>
      <button onClick={() => setValue('11')}>加载指定值</button>
    </>
  }
  render(<ControlledField />)
  fireEvent.click(screen.getByRole('button', { name: '加载范围' }))
  expect(screen.getAllByRole('spinbutton').map(input => (input as HTMLInputElement).value)).toEqual(['2', '8'])
  fireEvent.click(screen.getByRole('button', { name: '加载间隔' }))
  expect(within(screen.getAllByRole('combobox')[1]).getByText('4')).toBeTruthy()
  expect((screen.getByRole('spinbutton') as HTMLInputElement).value).toBe('9')
  fireEvent.click(screen.getByRole('button', { name: '加载列表' }))
  expect(within(screen.getByRole('combobox')).getByText('列表')).toBeTruthy()
  expect(screen.getByLabelText('父级接受值').textContent).toBe('3,7')
  fireEvent.click(screen.getByRole('button', { name: '加载自定义' }))
  expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('?')
  fireEvent.click(screen.getByRole('button', { name: '加载指定值' }))
  expect((screen.getByRole('spinbutton') as HTMLInputElement).value).toBe('11')
  expect(screen.getByLabelText('用户修改记录').textContent).toBe('')
  for (const [mode, draft] of [['范围', '2-8'], ['间隔', '4/9'], ['列表', '3,7'], ['自定义', '?'], ['指定值', '11']]) {
    await selectMode(mode)
    expect(screen.getByLabelText('父级接受值').textContent).toBe(draft)
  }
  expect(screen.getByLabelText('用户修改记录').textContent).toBe('2-8;4/9;3,7;?;11')
})

it('keeps accepted numeric drafts through incomplete and out-of-range edits and accepts the next valid input', async () => {
  render(<Field initialValue="5" />)
  for (const value of ['', '-', '1e', '-1', '60']) {
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value } })
    expect(screen.getByLabelText('已接受表达式').textContent).toBe('5')
  }
  await selectMode('任意值 (*)')
  await selectMode('指定值')
  expect((screen.getByRole('spinbutton') as HTMLInputElement).value).toBe('5')
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '7' } })
  expect(screen.getByLabelText('已接受表达式').textContent).toBe('7')
  await selectMode('间隔')
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '10' } })
  expect(screen.getByLabelText('已接受表达式').textContent).toBe('*/10')
  for (const value of ['', '0', '60']) {
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value } })
    expect(screen.getByLabelText('已接受表达式').textContent).toBe('*/10')
  }
  await selectMode('指定值')
  expect((screen.getByRole('spinbutton') as HTMLInputElement).value).toBe('7')
  await selectMode('间隔')
  expect((screen.getByRole('spinbutton') as HTMLInputElement).value).toBe('10')
})
