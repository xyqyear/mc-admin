import { mapSettings } from '@/features/settings/api'
import SettingsEditor, { SettingsSection } from '@/features/settings/ui/SettingsEditor'
import { NumberField } from '@/shared/components/FormFields'

export default function MapSettingsScreen() {
  return <SettingsEditor title="地图渲染设置" resource={mapSettings}>{(value, update) => <>
    <SettingsSection title="渲染与请求">
      <NumberField label="单次渲染区域上限" value={value.batch_size} min={1} max={256} step={1} required onChange={next => update({ ...value, batch_size: next ?? NaN })} />
      <NumberField label="渲染线程数" value={value.thread_count} min={1} max={64} step={1} required onChange={next => update({ ...value, thread_count: next ?? NaN })} />
      <NumberField label="瓦片请求超时（秒）" value={value.request_timeout_seconds} min={1} max={600} step={1} required onChange={next => update({ ...value, request_timeout_seconds: next ?? NaN })} />
    </SettingsSection>
    <SettingsSection title="区块裁剪">
      <NumberField label="裁剪预览有效期（秒）" value={value.prune_preview_ttl_seconds} min={1} max={86400} step={1} required onChange={next => update({ ...value, prune_preview_ttl_seconds: next ?? NaN })} />
      <NumberField label="区块清理默认阈值（秒）" value={value.prune_default_threshold_seconds} min={0} max={31536000} step={1} required onChange={next => update({ ...value, prune_default_threshold_seconds: next ?? NaN })} />
    </SettingsSection>
  </>}</SettingsEditor>
}
