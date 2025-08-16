import React from 'react'
import { Tag, Tooltip } from 'antd'
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  ToolOutlined,
} from '@ant-design/icons'

interface ServerStateTagProps {
  state: 'running' | 'paused' | 'stopped' | 'down'
}

const ServerStateTag: React.FC<ServerStateTagProps> = ({ state }) => {
  const getTagConfig = () => {
    switch (state) {
      case 'running':
        return {
          color: 'success',
          icon: <PlayCircleOutlined />,
          text: '运行中',
        }
      case 'paused':
        return {
          color: 'warning',
          icon: <PauseCircleOutlined />,
          text: '暂停',
        }
      case 'stopped':
        return {
          color: 'error',
          icon: <StopOutlined />,
          text: '停止',
        }
      case 'down':
        return {
          color: 'default',
          icon: <ToolOutlined />,
          text: '未创建',
        }
      default:
        return {
          color: 'default',
          icon: null,
          text: '未知',
        }
    }
  }

  const { color, icon, text } = getTagConfig()

  return (
    <Tooltip title={text}>
      <Tag color={color} icon={icon} className="flex items-center">
        {text}
      </Tag>
    </Tooltip>
  )
}

export default ServerStateTag
