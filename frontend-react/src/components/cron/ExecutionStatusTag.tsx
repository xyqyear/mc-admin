import React from 'react'
import { Loader2, CheckCircle2, XCircle, Square } from 'lucide-react'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface ExecutionStatusTagProps {
  status: string
  size?: 'small' | 'default'
}

const ExecutionStatusTag: React.FC<ExecutionStatusTagProps> = ({
  status,
  size = 'default',
}) => {
  const sizeClass = size === 'small' ? 'text-xs' : ''

  switch (status.toLowerCase()) {
    case 'running':
      return (
        <StatusBadge
          tone="info"
          badgeStyle="soft"
          className={sizeClass}
          iconSlot={<Loader2 className="h-3 w-3 animate-spin" />}
        >
          运行中
        </StatusBadge>
      )
    case 'completed':
      return (
        <StatusBadge tone="success" badgeStyle="soft" icon={CheckCircle2} className={sizeClass}>
          成功
        </StatusBadge>
      )
    case 'failed':
      return (
        <StatusBadge tone="danger" badgeStyle="soft" icon={XCircle} className={sizeClass}>
          失败
        </StatusBadge>
      )
    case 'cancelled':
      return (
        <Badge variant="outline" className={cn(sizeClass)}>
          <Square className="h-3 w-3" />
          取消
        </Badge>
      )
    default:
      return (
        <Badge variant="outline" className={cn(sizeClass)}>
          {status || '未知'}
        </Badge>
      )
  }
}

export default ExecutionStatusTag
