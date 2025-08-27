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
          text: 'Healthy',
          description: 'Server is running and responding normally'
        }
      case 'RUNNING':
        return {
          color: 'processing',
          icon: <PlayCircleOutlined />,
          text: 'Running',
          description: 'Server is running but health status unknown'
        }
      case 'STARTING':
        return {
          color: 'warning',
          icon: <LoadingOutlined spin />,
          text: 'Starting',
          description: 'Server is starting up'
        }
      case 'CREATED':
        return {
          color: 'default',
          icon: <PauseCircleOutlined />,
          text: 'Created',
          description: 'Container created but not running'
        }
      case 'EXISTS':
        return {
          color: 'warning',
          icon: <ExclamationCircleOutlined />,
          text: 'Exists',
          description: 'Server files exist but no container'
        }
      case 'REMOVED':
        return {
          color: 'error',
          icon: <MinusCircleOutlined />,
          text: 'Removed',
          description: 'Server has been removed'
        }
      default:
        return {
          color: 'default',
          icon: <ToolOutlined />,
          text: 'Unknown',
          description: 'Unknown server status'
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