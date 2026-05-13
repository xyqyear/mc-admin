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
    <div className={`flex flex-wrap items-center gap-2 ml-3 ${className}`}>
      <div className="flex items-center gap-3 shrink-0">
        {icon && (
          <span className="text-xl text-blue-600">
            {icon}
          </span>
        )}
        <h2 className="text-xl font-semibold tracking-tight whitespace-nowrap">
          {title}
        </h2>
        {serverTag && <StatusBadge tone="info">{serverTag}</StatusBadge>}
      </div>
      {actions}
    </div>
  )
}

export default PageHeader
