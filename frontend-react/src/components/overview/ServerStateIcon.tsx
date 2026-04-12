import React from 'react'
import {
  Play,
  Pause,
  Wrench,
  CheckCircle,
  Loader2,
  AlertCircle,
  MinusCircle,
} from 'lucide-react'
import type { ServerStatus } from '@/types/Server'

interface ServerStateIconProps {
  state: ServerStatus
  className?: string
  style?: React.CSSProperties
}

const iconMap: Record<string, { icon: React.ElementType; color: string }> = {
  HEALTHY: { icon: CheckCircle, color: '#52c41a' },
  RUNNING: { icon: Play, color: '#1677ff' },
  STARTING: { icon: Loader2, color: '#1677ff' },
  CREATED: { icon: Pause, color: '#ff4d4f' },
  EXISTS: { icon: AlertCircle, color: '#8c8c8c' },
  REMOVED: { icon: MinusCircle, color: '#ff4d4f' },
}

const defaultIcon = { icon: Wrench, color: '#8c8c8c' }

const ServerStateIcon: React.FC<ServerStateIconProps> = ({ state, className, style }) => {
  const { icon: Icon, color } = iconMap[state] || defaultIcon

  const spinClass = state === 'STARTING' ? 'animate-spin' : ''
  const combinedClassName = [spinClass, className].filter(Boolean).join(' ')

  return (
    <Icon
      className={combinedClassName}
      style={{ color, ...style }}
      size={14}
    />
  )
}

export default ServerStateIcon
