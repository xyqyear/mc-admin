import { playerSettings } from '@/features/settings/api'
import SettingsEditor, { SettingsSection } from '@/features/settings/ui/SettingsEditor'
import { FormField, NumberField, StringListField } from '@/shared/components/FormFields'
import { SimpleEditor } from '@/shared/editors'

export default function PlayerSettingsScreen() {
  return <SettingsEditor title="玩家设置" resource={playerSettings}>{(value, update) => <>
    <SettingsSection title="心跳与状态验证">
      <NumberField label="崩溃检测阈值（分钟）" value={value.heartbeat.crash_threshold_minutes} min={1} max={60} step={1} required onChange={next => update({ ...value, heartbeat: { ...value.heartbeat, crash_threshold_minutes: next ?? NaN } })} />
      <NumberField label="心跳更新间隔（秒）" value={value.heartbeat.heartbeat_interval_seconds} min={10} step={1} required onChange={next => update({ ...value, heartbeat: { ...value.heartbeat, heartbeat_interval_seconds: next ?? NaN } })} />
      <NumberField label="RCON 验证间隔（秒）" value={value.rcon_validation.validation_interval_seconds} min={30} step={1} required onChange={next => update({ ...value, rcon_validation: { validation_interval_seconds: next ?? NaN } })} />
      <NumberField label="皮肤请求超时（秒）" value={value.skin_fetcher.request_timeout_seconds} min={5} step={1} required onChange={next => update({ ...value, skin_fetcher: { request_timeout_seconds: next ?? NaN } })} />
    </SettingsSection>
    <SettingsSection title="Query 协议">
      <NumberField label="Query 请求超时（秒）" value={value.query.timeout} step="any" required onChange={next => update({ ...value, query: { ...value.query, timeout: next ?? NaN } })} />
      <FormField label="Query 命令模板" description="命令中的 25565 会替换为实际 Query 端口。">{id => <div id={id} role="group" aria-label="Query 命令模板"><SimpleEditor value={value.query.query_command} language="shell" height="240px" onChange={query_command => update({ ...value, query: { ...value.query, query_command: query_command ?? '' } })} /></div>}</FormField>
    </SettingsSection>
    <SettingsSection title="玩家过滤"><StringListField label="忽略的玩家名前缀" value={value.ignored_name_prefixes} onChange={ignored_name_prefixes => update({ ...value, ignored_name_prefixes })} description="忽略大小写，不将匹配前缀的玩家写入数据库。" /></SettingsSection>
  </>}</SettingsEditor>
}
