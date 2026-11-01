import type { ReactNode } from 'react'
import type { Sample } from '../contracts'

export function SampleValue<T>({ sample, failed = false, children }: {
  sample?: Sample<T>
  failed?: boolean
  children: (value: T) => ReactNode
}) {
  const quality = failed ? 'stale' : sample?.quality ?? 'pending'
  const message = failed ? '更新失败' : sample?.error ?? (quality === 'pending' ? '等待采样' : '暂不可用')
  if (sample?.value == null) return <span className="text-muted-foreground">{message}</span>
  return <span title={sample.sampled_at ? `采样时间：${new Date(sample.sampled_at).toLocaleString()}` : undefined}>
    {children(sample.value)}
    {quality !== 'ready' && <span className="text-xs text-muted-foreground ml-1">（{quality === 'stale' ? '数据已过期' : message}）</span>}
  </span>
}
