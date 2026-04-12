import React from 'react'
import { Play, Pause, Square } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

interface CronJobStatusTagProps {
  status: string
  size?: 'small' | 'default'
}

const CronJobStatusTag: React.FC<CronJobStatusTagProps> = ({
  status,
  size = 'default',
}) => {
  const getStatusConfig = () => {
    switch (status.toLowerCase()) {
      case 'active':
        return {
          className: 'bg-green-100 text-green-700 border-green-200',
          text: '运行中',
          icon: <Play className="h-3 w-3" />,
        }
      case 'paused':
        return {
          className: 'bg-orange-100 text-orange-700 border-orange-200',
          text: '已暂停',
          icon: <Pause className="h-3 w-3" />,
        }
      case 'cancelled':
        return {
          className: 'bg-red-100 text-red-700 border-red-200',
          text: '已取消',
          icon: <Square className="h-3 w-3" />,
        }
      default:
        return {
          className: '',
          text: status || '未知',
          icon: null,
        }
    }
  }

  const { className, text, icon } = getStatusConfig()

  return (
    <Badge
      variant="outline"
      className={`${className} ${size === 'small' ? 'text-xs' : ''}`}
    >
      {icon}
      {text}
    </Badge>
  )
}

export default CronJobStatusTag
