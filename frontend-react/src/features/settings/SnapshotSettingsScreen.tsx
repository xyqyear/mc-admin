import { snapshotSettings } from '@/features/settings/api'
import SettingsEditor, { SettingsSection } from '@/features/settings/ui/SettingsEditor'
import { BooleanField, NumberField, StringListField } from '@/shared/components/FormFields'

export default function SnapshotSettingsScreen() {
  return <SettingsEditor title="快照设置" resource={snapshotSettings}>{(value, update) => <>
    <SettingsSection title="备份时间限制">
      <BooleanField label="启用时间限制" value={value.time_restriction.enabled} onChange={enabled => update({ ...value, time_restriction: { ...value.time_restriction, enabled } })} />
      <NumberField label="备份前禁止秒数" value={value.time_restriction.before_seconds} min={0} max={300} step={1} required onChange={next => update({ ...value, time_restriction: { ...value.time_restriction, before_seconds: next ?? NaN } })} />
      <NumberField label="备份后禁止秒数" value={value.time_restriction.after_seconds} min={0} max={300} step={1} required onChange={next => update({ ...value, time_restriction: { ...value.time_restriction, after_seconds: next ?? NaN } })} />
    </SettingsSection>
    <SettingsSection title="世界恢复预览">
      <NumberField label="预览会话存活时间（秒）" value={value.world_restore.preview_session_ttl_seconds} min={60} step={1} required onChange={next => update({ ...value, world_restore: { ...value.world_restore, preview_session_ttl_seconds: next ?? NaN } })} />
      <NumberField label="预览清理轮询间隔（秒）" value={value.world_restore.preview_janitor_interval_seconds} min={10} step={1} required onChange={next => update({ ...value, world_restore: { ...value.world_restore, preview_janitor_interval_seconds: next ?? NaN } })} />
      <NumberField label="预览平均 region 字节数" value={value.world_restore.preview_avg_region_bytes} min={1} step={1} required onChange={next => update({ ...value, world_restore: { ...value.world_restore, preview_avg_region_bytes: next ?? NaN } })} />
    </SettingsSection>
    <SettingsSection title="备份排除路径"><StringListField label="忽略路径" value={value.ignored_paths} onChange={ignored_paths => update({ ...value, ignored_paths })} description="相对于服务器数据目录；支持完整路径段 <LEVEL_NAME>，不支持通配符。地图快照及回档不使用这些排除设置。" /></SettingsSection>
  </>}</SettingsEditor>
}
