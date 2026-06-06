import React from 'react'
import { AlertTriangle, ShieldAlert } from 'lucide-react'
import { useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useSelfCheckHealth } from '@/hooks/useSelfCheckHealth'
import { cn } from '@/lib/utils'

export const SelfCheckGlobalIndicator: React.FC = () => {
  const navigate = useNavigate()
  const { status, issueCount, criticalCount, warningCount, isLoading } =
    useSelfCheckHealth()

  if (isLoading || issueCount === 0) {
    return null
  }

  const critical = status === 'critical'

  return (
    <div
      className={cn(
        'flex items-center gap-3 border-b px-4 py-2 text-sm',
        critical
          ? 'border-red-200 bg-red-50 text-red-900 dark:border-red-900/70 dark:bg-red-950/30 dark:text-red-200'
          : 'border-yellow-200 bg-yellow-50 text-yellow-900 dark:border-yellow-900/70 dark:bg-yellow-950/30 dark:text-yellow-200'
      )}
    >
      {critical ? (
        <ShieldAlert className="h-4 w-4 shrink-0" />
      ) : (
        <AlertTriangle className="h-4 w-4 shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        系统自检存在未修复问题
      </div>
      <div className="hidden shrink-0 items-center gap-2 sm:flex">
        {criticalCount > 0 && (
          <StatusBadge tone="danger" badgeStyle="soft">
            严重 {criticalCount}
          </StatusBadge>
        )}
        {warningCount > 0 && (
          <StatusBadge tone="warning" badgeStyle="soft">
            警告 {warningCount}
          </StatusBadge>
        )}
      </div>
      <Button
        variant="outline"
        size="sm"
        className="shrink-0 bg-background/80"
        onClick={() => navigate('/')}
      >
        查看
      </Button>
    </div>
  )
}

export default SelfCheckGlobalIndicator
