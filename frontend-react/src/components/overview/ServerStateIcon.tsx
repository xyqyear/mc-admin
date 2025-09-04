import React from 'react'
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

interface ServerStateIconProps {
  state: ServerStatus
  className?: string
  style?: React.CSSProperties
}

const ServerStateIcon: React.FC<ServerStateIconProps> = ({ state, className, style }) => {
  const getIconConfig = () => {
    switch (state) {
      case 'HEALTHY':
        return {
          icon: <CheckCircleOutlined />,
          color: '#52c41a' // success green
        }
      case 'RUNNING':
        return {
          icon: <PlayCircleOutlined />,
          color: '#1677ff' // processing blue
        }
      case 'STARTING':
        return {
          icon: <LoadingOutlined spin />,
          color: '#1677ff' // processing blue
        }
      case 'CREATED':
        return {
          icon: <PauseCircleOutlined />,
          color: '#ff4d4f' // error red
        }
      case 'EXISTS':
        return {
          icon: <ExclamationCircleOutlined />,
          color: '#8c8c8c' // default gray
        }
      case 'REMOVED':
        return {
          icon: <MinusCircleOutlined />,
          color: '#ff4d4f' // red
        }
      default:
        return {
          icon: <ToolOutlined />,
          color: '#8c8c8c' // default gray
        }
    }
  }

  const { icon, color } = getIconConfig()

  return React.cloneElement(icon as React.ReactElement, {
    className,
    style: { color, ...style }
  })
}

export default ServerStateIcon