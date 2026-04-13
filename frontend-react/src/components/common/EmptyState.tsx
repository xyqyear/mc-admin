import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface EmptyStateProps {
  icon?: LucideIcon
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
  className?: string
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center py-8 text-center',
        className
      )}
    >
      {Icon && <Icon className="mb-2 h-10 w-10 text-muted-foreground/30" />}
      <div className="text-muted-foreground">{title}</div>
      {description && (
        <div className="mt-1 text-sm text-muted-foreground/70">{description}</div>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

export default EmptyState
