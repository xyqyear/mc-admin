import React from 'react'
import { Tag, Tooltip } from 'antd'
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  ToolOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
  ExclamationCircleOutlined,
  MinusCircleOutlined,
} from '@ant-design/icons'
import type { ServerStatus } from '@/types/Server'

interface ServerStateTagProps {
  state: ServerStatus
}

const ServerStateTag: React.FC<ServerStateTagProps> = ({ state }) => {
  const getTagConfig = () => {
    switch (state) {
      case 'HEALTHY':
        return {
          color: 'success',
          icon: <CheckCircleOutlined />,
          text: '健康',
          description: '服务器正在运行且响应正常'
        }
      case 'RUNNING':
        return {
          color: 'processing',
          icon: <PlayCircleOutlined />,
          text: '运行中',
          description: '服务器正在运行但健康状态未知'
        }
      case 'STARTING':
        return {
          color: 'processing',
          icon: <LoadingOutlined spin />,
          text: '启动中',
          description: '服务器正在启动'
        }
      case 'CREATED':
        return {
          color: 'error',
          icon: <PauseCircleOutlined />,
          text: '已停止',
          description: '容器已创建但未运行'
        }
      case 'EXISTS':
        return {
          color: 'default',
          icon: <ExclamationCircleOutlined />,
          text: '未创建',
          description: '服务器文件存在但无容器'
        }
      case 'REMOVED':
        return {
          color: 'red',
          icon: <MinusCircleOutlined />,
          text: '已删除',
          description: '服务器已被删除'
        }
      default:
        return {
          color: 'default',
          icon: <ToolOutlined />,
          text: '未知',
          description: '未知服务器状态'
        }
    }
  }

  const { color, icon, text, description } = getTagConfig()

  return (
    <Tooltip title={description}>
      <Tag color={color} icon={icon}>
        {text}
      </Tag>
    </Tooltip>
  )
}

export default ServerStateTag