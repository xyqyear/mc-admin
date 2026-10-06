import { useState } from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import CronExpressionBuilder from './CronExpressionBuilder'

it('changes the preset without submitting until the user explicitly saves', () => {
  const submit = vi.fn(event => event.preventDefault())
  const change = vi.fn()
  render(<form onSubmit={submit}>
    <CronExpressionBuilder cronValue="0 0 * * *" onCronChange={change} />
    <button type="submit">保存任务</button>
  </form>)
  fireEvent.click(screen.getByRole('button', { name: /每30分钟/ }))
  expect(change).toHaveBeenCalledWith('*/30 * * * *')
  expect(submit).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '保存任务' }))
  expect(submit).toHaveBeenCalledOnce()
})

it('retains controlled five-field and seconds values across external loads and raw-to-visual round trips', async () => {
  function ControlledBuilder() {
    const [cron, setCron] = useState('5 6 * * 1')
    const [second, setSecond] = useState('15')
    const [edits, setEdits] = useState<string[]>([])
    return <>
      <CronExpressionBuilder cronValue={cron} secondValue={second}
        onCronChange={value => { setCron(value); setEdits(previous => [...previous, `cron:${value}`]) }}
        onSecondChange={value => { setSecond(value); setEdits(previous => [...previous, `second:${value}`]) }} />
      <output aria-label="已接受Cron">{cron}</output>
      <output aria-label="已接受秒">{second}</output>
      <output aria-label="用户修改记录">{edits.join(';')}</output>
      <button onClick={() => { setCron('*/10 4 * * 7'); setSecond('20') }}>加载其他任务</button>
    </>
  }
  async function mode(name: string) {
    fireEvent.click(screen.getAllByRole('combobox')[0])
    const option = await screen.findByRole('option', { name })
    fireEvent.pointerDown(option)
    fireEvent.click(option)
  }
  render(<ControlledBuilder />)
  await mode('原始表达式')
  const cronInput = () => screen.getByPlaceholderText('输入Cron表达式，例如: 0 0 * * *') as HTMLInputElement
  const secondInput = () => screen.getByPlaceholderText('输入秒字段，例如: 30') as HTMLInputElement
  expect(cronInput().value).toBe('5 6 * * 1')
  expect(secondInput().value).toBe('15')
  expect(screen.getByLabelText('用户修改记录').textContent).toBe('')
  fireEvent.change(cronInput(), { target: { value: '0 9 1 2 0' } })
  fireEvent.change(secondInput(), { target: { value: '0' } })
  expect(screen.getByLabelText('已接受Cron').textContent).toBe('0 9 1 2 0')
  expect(screen.getByLabelText('已接受秒').textContent).toBe('0')
  fireEvent.click(screen.getByRole('button', { name: '加载其他任务' }))
  expect(cronInput().value).toBe('*/10 4 * * 7')
  expect(secondInput().value).toBe('20')
  await mode('可视化配置')
  const field = (label: string) => screen.getByText(label).parentElement!.parentElement!
  expect((within(field('分钟 (0-59)')).getByRole('spinbutton') as HTMLInputElement).value).toBe('10')
  expect((within(field('小时 (0-23)')).getByRole('spinbutton') as HTMLInputElement).value).toBe('4')
  expect((within(field('秒 (0-59)')).getByRole('spinbutton') as HTMLInputElement).value).toBe('20')
  expect(screen.getByLabelText('用户修改记录').textContent).toBe('cron:0 9 1 2 0;second:0')
  fireEvent.change(within(field('小时 (0-23)')).getByRole('spinbutton'), { target: { value: '12' } })
  fireEvent.change(within(field('秒 (0-59)')).getByRole('spinbutton'), { target: { value: '0' } })
  expect(screen.getByLabelText('已接受Cron').textContent).toBe('*/10 12 * * 7')
  expect(screen.getByLabelText('已接受秒').textContent).toBe('0')
  await mode('原始表达式')
  expect(cronInput().value).toBe('*/10 12 * * 7')
  expect(secondInput().value).toBe('0')
  expect(screen.getByLabelText('用户修改记录').textContent).toBe('cron:0 9 1 2 0;second:0;cron:*/10 12 * * 7;second:0')
})
