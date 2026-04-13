import React from 'react'
import { StatusBadge, type BadgeTone } from '@/components/common/StatusBadge'
import type { ServerStatus } from '@/types/Server'
import ServerStateIcon from '@/components/overview/ServerStateIcon'

interface ServerStateTagProps {
  state: ServerStatus
}

const tagConfigs: Record<string, { text: string; description: string; tone: BadgeTone }> = {
  HEALTHY: {
    text: '健康',
    description: '服务器正在运行且响应正常',
    tone: 'success',
  },
  RUNNING: {
    text: '运行中',
    description: '服务器正在运行但健康状态未知',
    tone: 'info',
  },
  STARTING: {
    text: '启动中',
    description: '服务器正在启动',
    tone: 'info',
  },
  CREATED: {
    text: '已停止',
    description: '容器已创建但未运行',
    tone: 'danger',
  },
  EXISTS: {
    text: '未创建',
    description: '服务器文件存在但无容器',
    tone: 'neutral',
  },
  REMOVED: {
    text: '已删除',
    description: '服务器已被删除',
    tone: 'danger',
  },
}

const defaultConfig = {
  text: '未知',
  description: '未知服务器状态',
  tone: 'neutral' as BadgeTone,
}

const ServerStateTag: React.FC<ServerStateTagProps> = ({ state }) => {
  const { text, description, tone } = tagConfigs[state] || defaultConfig

  return (
    <StatusBadge
      tone={tone}
      title={description}
      iconSlot={<ServerStateIcon state={state} className="mr-1" />}
    >
      {text}
    </StatusBadge>
  )
}

export default ServerStateTag
