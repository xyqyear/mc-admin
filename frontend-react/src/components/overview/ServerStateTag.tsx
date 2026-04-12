import React from 'react'
import { Badge } from '@/components/ui/badge'
import type { ServerStatus } from '@/types/Server'
import ServerStateIcon from '@/components/overview/ServerStateIcon'

interface ServerStateTagProps {
  state: ServerStatus
}

const tagConfigs: Record<string, { text: string; description: string; className: string }> = {
  HEALTHY: {
    text: '健康',
    description: '服务器正在运行且响应正常',
    className: 'bg-green-100 text-green-800 hover:bg-green-100',
  },
  RUNNING: {
    text: '运行中',
    description: '服务器正在运行但健康状态未知',
    className: 'bg-blue-100 text-blue-800 hover:bg-blue-100',
  },
  STARTING: {
    text: '启动中',
    description: '服务器正在启动',
    className: 'bg-blue-100 text-blue-800 hover:bg-blue-100',
  },
  CREATED: {
    text: '已停止',
    description: '容器已创建但未运行',
    className: 'bg-red-100 text-red-800 hover:bg-red-100',
  },
  EXISTS: {
    text: '未创建',
    description: '服务器文件存在但无容器',
    className: 'bg-gray-100 text-gray-800 hover:bg-gray-100',
  },
  REMOVED: {
    text: '已删除',
    description: '服务器已被删除',
    className: 'bg-red-100 text-red-800 hover:bg-red-100',
  },
}

const defaultConfig = {
  text: '未知',
  description: '未知服务器状态',
  className: 'bg-gray-100 text-gray-800 hover:bg-gray-100',
}

const ServerStateTag: React.FC<ServerStateTagProps> = ({ state }) => {
  const { text, description, className } = tagConfigs[state] || defaultConfig

  return (
    <Badge className={className} title={description}>
      <ServerStateIcon state={state} className="mr-1" />
      {text}
    </Badge>
  )
}

export default ServerStateTag
