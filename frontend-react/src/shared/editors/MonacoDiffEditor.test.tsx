import { useEffect } from 'react'
import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import MonacoDiffEditor from './MonacoDiffEditor'

vi.mock('@/shared/theme-provider', () => ({ useMonacoTheme: () => 'light' }))
vi.mock('@monaco-editor/react', () => ({ DiffEditor: ({ onMount }: { onMount?: (editor: object) => void }) => {
  useEffect(() => { onMount?.({}) }, [onMount])
  return <div>diff editor</div>
} }))
afterEach(() => vi.restoreAllMocks())

it('labels both versions and keeps configuration contents out of mount logging', () => {
  const log = vi.spyOn(console, 'log').mockImplementation(() => {})
  const mounted = vi.fn()
  render(<MonacoDiffEditor original="RCON_PASSWORD: original-private-value" modified="RCON_PASSWORD: changed-private-value" originalTitle="编辑起点" modifiedTitle="最新在线配置" onMount={mounted} />)
  expect(screen.getByText('编辑起点')).toBeTruthy()
  expect(screen.getByText('最新在线配置')).toBeTruthy()
  expect(mounted).toHaveBeenCalledOnce()
  expect(log).not.toHaveBeenCalled()
})
