import { selfCheckSettings } from '@/features/settings/api'
import type { SelfCheckSettings } from '@/features/settings/contracts'
import SettingsEditor, { SettingsSection } from '@/features/settings/ui/SettingsEditor'
import { BooleanField, NumberField, StringListField } from '@/shared/components/FormFields'

const checkLabels: Record<keyof SelfCheckSettings['checks'], string> = {
  backup_restic_configured: 'Restic 配置', backup_restic_reachable: 'Restic 仓库连通性',
  backup_server_snapshot_coverage: '服务器快照覆盖', backup_server_snapshot_freshness: '服务器快照新鲜度',
  storage_backup_repository_usage: '备份仓库磁盘使用率', storage_server_directory_usage: '服务器目录磁盘使用率',
  locks_python_restic_active: '应用备份任务锁', locks_repo_restic_active: 'Restic 仓库活动锁',
  dns_drift: 'DNS 与路由差异', dependency_binaries: '外部程序依赖', log_monitor_active: '日志监听状态',
  server_backup_mod_removed: '备份 Mod 与插件', server_game_port_consistency: '游戏端口一致性',
  files_permission_consistency: '文件所有者一致性', server_filesystem_db_sync: '服务器登记一致性',
}

export default function SelfCheckSettingsScreen() {
  return <SettingsEditor title="自检设置" resource={selfCheckSettings}>{(value, update) => <>
    <SettingsSection title="检查项目"><div className="grid gap-5 sm:grid-cols-2">{(Object.keys(checkLabels) as (keyof SelfCheckSettings['checks'])[]).map(key => <BooleanField key={key} label={checkLabels[key]} value={value.checks[key]} onChange={enabled => update({ ...value, checks: { ...value.checks, [key]: enabled } })} />)}</div></SettingsSection>
    <SettingsSection title="阈值与记录">
      <NumberField label="快照新鲜度上限（分钟）" value={value.snapshot_freshness_minutes} min={1} step={1} required onChange={next => update({ ...value, snapshot_freshness_minutes: next ?? NaN })} />
      <NumberField label="备份仓库磁盘使用率阈值（%）" value={value.backup_repository_usage_percent} min={1} max={100} step="any" required onChange={next => update({ ...value, backup_repository_usage_percent: next ?? NaN })} />
      <NumberField label="服务器目录磁盘使用率阈值（%）" value={value.server_directory_usage_percent} min={1} max={100} step="any" required onChange={next => update({ ...value, server_directory_usage_percent: next ?? NaN })} />
      <NumberField label="自检记录保留天数" value={value.retention_runs_keep_days} min={1} step={1} required onChange={next => update({ ...value, retention_runs_keep_days: next ?? NaN })} />
      <NumberField label="所有者扫描最大异常数" value={value.permission_scan_max_entries} min={100} step={1} required onChange={next => update({ ...value, permission_scan_max_entries: next ?? NaN })} />
      <StringListField label="备份 Mod 或插件 ID" value={value.backup_mod_ids} onChange={backup_mod_ids => update({ ...value, backup_mod_ids })} />
    </SettingsSection>
    <SettingsSection title="事件触发">
      <BooleanField label="创建服务器后自检" value={value.event_triggers.after_server_created} onChange={next => update({ ...value, event_triggers: { ...value.event_triggers, after_server_created: next } })} />
      <BooleanField label="填充服务器数据后自检" value={value.event_triggers.after_server_populated} onChange={next => update({ ...value, event_triggers: { ...value.event_triggers, after_server_populated: next } })} />
      <BooleanField label="世界恢复后自检" value={value.event_triggers.after_world_restored} onChange={next => update({ ...value, event_triggers: { ...value.event_triggers, after_world_restored: next } })} />
      <BooleanField label="世界回滚后自检" value={value.event_triggers.after_world_rolled_back} onChange={next => update({ ...value, event_triggers: { ...value.event_triggers, after_world_rolled_back: next } })} />
    </SettingsSection>
  </>}</SettingsEditor>
}
