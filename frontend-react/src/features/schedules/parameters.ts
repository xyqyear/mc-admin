import type { BackupParameters, JobParameters } from '@/features/schedules/contracts'

export function jobParameters(identifier: string, stored?: Record<string, unknown>): JobParameters | null {
  switch (identifier) {
    case 'restart_server': return { identifier, params: { server_id: typeof stored?.server_id === 'string' ? stored.server_id : '' } }
    case 'backup': return { identifier, params: { enable_forget: true, prune: true, ...stored } as BackupParameters }
    case 'self_check': return { identifier, params: { scope: typeof stored?.scope === 'string' ? stored.scope : 'global' } }
    default: return null
  }
}

export function jobParameterError(value: JobParameters): string | undefined {
  if (value.identifier === 'restart_server' && !value.params.server_id.trim()) return '请输入服务器 ID'
  if (value.identifier !== 'backup') return
  const params = value.params
  if (params.path && !params.server_id) return '指定备份路径时必须填写服务器 ID'
  if (params.enable_forget && [params.keep_last, params.keep_hourly, params.keep_daily, params.keep_weekly, params.keep_monthly, params.keep_yearly, params.keep_within, params.keep_tag?.length ? params.keep_tag : undefined].every(item => item == null || typeof item === 'string' && item.trim() === '')) return '启用快照清理时至少需要指定一个保留策略'
}
