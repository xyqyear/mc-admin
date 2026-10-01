import { fireEvent, render, screen } from '@testing-library/react'
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
