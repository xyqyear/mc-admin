import { logParserSettings } from '@/features/settings/api'
import SettingsEditor, { SettingsSection } from '@/features/settings/ui/SettingsEditor'
import { StringListField, TextAreaField } from '@/shared/components/FormFields'

export default function LogParserSettingsScreen() {
  return <SettingsEditor title="日志解析设置" resource={logParserSettings}>{(value, update) => <>
    <SettingsSection title="玩家识别"><StringListField label="UUID 解析规则" value={value.uuid_patterns} onChange={uuid_patterns => update({ ...value, uuid_patterns })} multiline orderable description="每条规则至少包含玩家名和 UUID 两个捕获组。" /></SettingsSection>
    <SettingsSection title="玩家事件">
      <TextAreaField label="玩家加入解析规则" value={value.join_pattern} onChange={join_pattern => update({ ...value, join_pattern })} rows={4} description="至少包含一个玩家名捕获组。" />
      <TextAreaField label="玩家离开解析规则" value={value.leave_pattern} onChange={leave_pattern => update({ ...value, leave_pattern })} rows={4} description="至少包含一个玩家名捕获组。" />
      <TextAreaField label="聊天消息解析规则" value={value.chat_pattern} onChange={chat_pattern => update({ ...value, chat_pattern })} rows={4} description="依次捕获可选前缀、玩家名和消息，共三个捕获组。" />
      <StringListField label="成就解析规则" value={value.achievement_patterns} onChange={achievement_patterns => update({ ...value, achievement_patterns })} multiline orderable description="至少包含玩家名和成就名称两个捕获组。" />
    </SettingsSection>
    <SettingsSection title="服务器事件"><TextAreaField label="服务器停止解析规则" value={value.server_stop_pattern} onChange={server_stop_pattern => update({ ...value, server_stop_pattern })} rows={4} /></SettingsSection>
  </>}</SettingsEditor>
}
