import React from 'react'
import { Loader2, CheckCircle2, XCircle, Square } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

interface ExecutionStatusTagProps {
  status: string
  size?: 'small' | 'default'
}

const ExecutionStatusTag: React.FC<ExecutionStatusTagProps> = ({
  status,
  size = 'default',
}) => {
  const getStatusConfig = () => {
    switch (status.toLowerCase()) {
      case 'running':
        return {
          className: 'bg-blue-100 text-blue-700 border-blue-200',
          text: '运行中',
          icon: <Loader2 className="h-3 w-3 animate-spin" />,
        }
      case 'completed':
        return {
          className: 'bg-green-100 text-green-700 border-green-200',
          text: '成功',
          icon: <CheckCircle2 className="h-3 w-3" />,
        }
      case 'failed':
        return {
          className: 'bg-red-100 text-red-700 border-red-200',
          text: '失败',
          icon: <XCircle className="h-3 w-3" />,
        }
      case 'cancelled':
        return {
          className: '',
          text: '取消',
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

export default ExecutionStatusTag
