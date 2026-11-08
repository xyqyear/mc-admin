import type { JobParameters } from '@/features/schedules/contracts'
import { jobParameterError } from '@/features/schedules/parameters'
import { BooleanField, NumberField, StringListField, TextField } from '@/shared/components/FormFields'
import { Alert, AlertDescription } from '@/shared/ui/alert'

export default function CronJobParameters({ value, onChange }: { value: JobParameters; onChange: (value: JobParameters) => void }) {
  if (value.identifier === 'self_check') return <p className="text-sm text-muted-foreground">自检任务使用系统自检设置，无需额外参数。</p>
  const error = jobParameterError(value)
  return <div className="space-y-4" onKeyDown={event => {
    if (event.key === 'Enter' && !(event.target instanceof HTMLTextAreaElement)) event.preventDefault()
  }}>
    {value.identifier === 'restart_server'
      ? <TextField label="服务器 ID" value={value.params.server_id} onChange={server_id => onChange({ identifier: 'restart_server', params: { server_id } })} required />
      : <>
        <TextField label="服务器 ID" value={value.params.server_id ?? ''} onChange={server_id => onChange({ ...value, params: { ...value.params, server_id: server_id || undefined } })} description="留空表示备份所有服务器。" />
        <TextField label="备份路径" value={value.params.path ?? ''} onChange={path => onChange({ ...value, params: { ...value.params, path: path || undefined } })} description="可选的服务器数据目录内路径。" />
        <BooleanField label="备份后清理旧快照" value={value.params.enable_forget} onChange={enable_forget => onChange({ ...value, params: { ...value.params, enable_forget } })} />
        <div className="grid gap-4 sm:grid-cols-2">
          <NumberField label="保留最近快照数" value={value.params.keep_last} step={1} onChange={keep_last => onChange({ ...value, params: { ...value.params, keep_last } })} />
          <NumberField label="每小时保留" value={value.params.keep_hourly} step={1} onChange={keep_hourly => onChange({ ...value, params: { ...value.params, keep_hourly } })} />
          <NumberField label="每天保留" value={value.params.keep_daily} step={1} onChange={keep_daily => onChange({ ...value, params: { ...value.params, keep_daily } })} />
          <NumberField label="每周保留" value={value.params.keep_weekly} step={1} onChange={keep_weekly => onChange({ ...value, params: { ...value.params, keep_weekly } })} />
          <NumberField label="每月保留" value={value.params.keep_monthly} step={1} onChange={keep_monthly => onChange({ ...value, params: { ...value.params, keep_monthly } })} />
          <NumberField label="每年保留" value={value.params.keep_yearly} step={1} onChange={keep_yearly => onChange({ ...value, params: { ...value.params, keep_yearly } })} />
        </div>
        <TextField label="按时间范围保留" value={value.params.keep_within ?? ''} onChange={keep_within => onChange({ ...value, params: { ...value.params, keep_within: keep_within || undefined } })} placeholder="例如 4d 或 2y5m7d3h" />
        <StringListField label="保留标签" value={value.params.keep_tag ?? []} onChange={keep_tag => onChange({ ...value, params: { ...value.params, keep_tag: keep_tag.length ? keep_tag : undefined } })} />
        <BooleanField label="清理未使用的数据块" value={value.params.prune} onChange={prune => onChange({ ...value, params: { ...value.params, prune } })} />
        <TextField label="Uptime Kuma 推送 URL" value={value.params.uptimekuma_url ?? ''} onChange={uptimekuma_url => onChange({ ...value, params: { ...value.params, uptimekuma_url: uptimekuma_url || undefined } })} />
      </>}
    {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
  </div>
}
