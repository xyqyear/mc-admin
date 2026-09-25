import type { RegistrationStatus } from '@/features/schedules/contracts'

const labels: Record<RegistrationStatus, string> = {
  registered: '调度已注册',
  pending: '等待注册，暂未调度',
  failed: '注册失败，暂未调度',
  blocked: '调度受阻，需要处理',
  inactive: '未注册调度',
}

export function CronRegistrationStatus({ status, error }: {
  status?: RegistrationStatus
  error?: string | null
}) {
  if (!status) return null
  return <div className={status === 'failed' || status === 'blocked' ? 'text-xs text-destructive' : 'text-xs text-muted-foreground'}>
    <span>{labels[status]}</span>
    {error && <p>{error}</p>}
  </div>
}
