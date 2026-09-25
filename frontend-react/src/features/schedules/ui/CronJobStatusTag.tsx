import React from 'react'
import { Play, Pause, Square } from 'lucide-react'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { Badge } from '@/shared/ui/badge'
import { cn } from '@/shared/lib/utils'

interface CronJobStatusTagProps {
  status: string
  size?: 'small' | 'default'
}

const CronJobStatusTag: React.FC<CronJobStatusTagProps> = ({
  status,
  size = 'default',
}) => {
  const sizeClass = size === 'small' ? 'text-xs' : ''

  switch (status.toLowerCase()) {
    case 'active':
      return (
        <StatusBadge tone="success" badgeStyle="soft" icon={Play} className={sizeClass}>
          已启用
        </StatusBadge>
      )
    case 'paused':
      return (
        <StatusBadge tone="warning" badgeStyle="soft" icon={Pause} className={sizeClass}>
          已暂停
        </StatusBadge>
      )
    case 'cancelled':
      return (
        <StatusBadge tone="danger" badgeStyle="soft" icon={Square} className={sizeClass}>
          已取消
        </StatusBadge>
      )
    default:
      return (
        <Badge variant="outline" className={cn(sizeClass)}>
          {status || '未知'}
        </Badge>
      )
  }
}

export default CronJobStatusTag
