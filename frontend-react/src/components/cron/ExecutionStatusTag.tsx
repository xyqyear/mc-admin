import React from 'react'
import { Tag } from 'antd'
import {
  LoadingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  StopOutlined
} from '@ant-design/icons'

interface ExecutionStatusTagProps {
  status: string
  size?: 'small' | 'default'
}

const ExecutionStatusTag: React.FC<ExecutionStatusTagProps> = ({
  status,
  size = 'default'
}) => {
  const getStatusConfig = () => {
    switch (status.toLowerCase()) {
      case 'running':
        return {
          color: 'processing',
          text: '运行中',
          icon: <LoadingOutlined spin />
        }
      case 'completed':
        return {
          color: 'success',
          text: '成功',
          icon: <CheckCircleOutlined />
        }
      case 'failed':
        return {
          color: 'error',
          text: '失败',
          icon: <CloseCircleOutlined />
        }
      case 'cancelled':
        return {
          color: 'default',
          text: '取消',
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

export default ExecutionStatusTag