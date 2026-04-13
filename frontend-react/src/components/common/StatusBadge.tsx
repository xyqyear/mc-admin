import type { ComponentProps, ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral'
export type BadgeStyle = 'solid' | 'soft'

const solidToneClasses: Record<BadgeTone, string> = {
  success: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  warning: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
  danger: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  info: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  neutral: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
}

const softToneClasses: Record<BadgeTone, string> = {
  success:
    'bg-green-50 text-green-700 border-green-200 dark:bg-green-950/40 dark:text-green-300 dark:border-green-900',
  warning:
    'bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-950/40 dark:text-yellow-300 dark:border-yellow-900',
  danger:
    'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-300 dark:border-red-900',
  info: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-900',
  neutral:
    'bg-gray-50 text-gray-700 border-gray-200 dark:bg-gray-900/40 dark:text-gray-300 dark:border-gray-700',
}

interface StatusBadgeProps extends Omit<ComponentProps<typeof Badge>, 'variant'> {
  tone: BadgeTone
  badgeStyle?: BadgeStyle
  icon?: LucideIcon
  iconSlot?: ReactNode
}

export function StatusBadge({
  tone,
  badgeStyle = 'solid',
  icon: Icon,
  iconSlot,
  className,
  children,
  ...props
}: StatusBadgeProps) {
  const toneClass = badgeStyle === 'soft' ? softToneClasses[tone] : solidToneClasses[tone]
  return (
    <Badge className={cn(toneClass, className)} {...props}>
      {iconSlot ?? (Icon && <Icon className="h-3 w-3" />)}
      {children}
    </Badge>
  )
}

