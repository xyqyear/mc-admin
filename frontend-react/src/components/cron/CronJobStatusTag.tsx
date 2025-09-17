import React from 'react'
import { Tag } from 'antd'
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined
} from '@ant-design/icons'

interface CronJobStatusTagProps {
  status: string
  size?: 'small' | 'default'
}

const CronJobStatusTag: React.FC<CronJobStatusTagProps> = ({
  status,
  size = 'default'
}) => {
  const getStatusConfig = () => {
    switch (status.toLowerCase()) {
      case 'active':
        return {
          color: 'green',
          text: '运行中',
          icon: <PlayCircleOutlined />
        }
      case 'paused':
        return {
          color: 'orange',
          text: '已暂停',
          icon: <PauseCircleOutlined />
        }
      case 'cancelled':
        return {
          color: 'red',
          text: '已取消',
          icon: <StopOutlined />
        }
      default:
        return {
          color: 'default',
          text: status || '未知',
          icon: null
        }
    }
  }

  const { color, text, icon } = getStatusConfig()

  return (
    <Tag
      color={color}
      icon={icon}
      className={size === 'small' ? 'text-xs' : ''}
    >
      {text}
    </Tag>
  )
}

export default CronJobStatusTag