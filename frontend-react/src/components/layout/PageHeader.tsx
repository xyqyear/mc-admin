import React from 'react'
import { StatusBadge } from '@/components/common/StatusBadge'

interface PageHeaderProps {
  title: string
  icon?: React.ReactNode
  actions?: React.ReactNode
  serverTag?: string
  className?: string
}

const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  icon,
  actions,
  serverTag,
  className = ''
}) => {
  return (
    <div className={`flex justify-between items-center ml-3 ${className}`}>
      <div className="flex items-center gap-3">
        {icon && (
          <span className="text-xl text-blue-600">
            {icon}
          </span>
        )}
        <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
        {serverTag && <StatusBadge tone="info">{serverTag}</StatusBadge>}
      </div>
      {actions && (
        <div className="flex items-center gap-2">
          {actions}
        </div>
      )}
    </div>
  )
}

export default PageHeader
