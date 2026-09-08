import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'

import ExecutionStatusTag from './ExecutionStatusTag'

it('distinguishes a skipped execution from a successful backup', () => {
  const { rerender } = render(<ExecutionStatusTag status="skipped" />)
  expect(screen.getByText('跳过')).toBeTruthy()
  expect(screen.queryByText('成功')).toBeNull()

  rerender(<ExecutionStatusTag status="completed" />)
  expect(screen.getByText('成功')).toBeTruthy()
  expect(screen.queryByText('跳过')).toBeNull()
})
