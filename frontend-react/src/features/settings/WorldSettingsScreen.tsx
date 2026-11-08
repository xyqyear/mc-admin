import { worldSettings } from '@/features/settings/api'
import SettingsEditor, { SettingsSection } from '@/features/settings/ui/SettingsEditor'
import { NumberField, StringMapField } from '@/shared/components/FormFields'

export default function WorldSettingsScreen() {
  return <SettingsEditor title="世界设置" resource={worldSettings}>{(value, update) => <>
    <SettingsSection title="世界目录扫描">
      <NumberField label="区域清单扫描线程数" value={value.region_stat_workers} min={1} max={256} step={1} required onChange={next => update({ ...value, region_stat_workers: next ?? NaN })} />
      <NumberField label="维度扫描最大深度" value={value.dimension_max_depth_from_world_root} min={0} max={32} step={1} required onChange={next => update({ ...value, dimension_max_depth_from_world_root: next ?? NaN })} />
    </SettingsSection>
    <SettingsSection title="维度显示名称"><StringMapField label="维度名称" value={value.dimension_labels} onChange={dimension_labels => update({ ...value, dimension_labels })} /></SettingsSection>
  </>}</SettingsEditor>
}
