import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Clock, Settings } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip'
import { Spinner } from '@/components/ui/spinner'
import CronExpressionDisplay from '@/components/cron/CronExpressionDisplay'
import type { RestartScheduleResponse } from '@/hooks/api/serverApi'
import { CronJobStatusTag } from '@/components/cron'

interface ServerRestartScheduleCardProps {
  restartSchedule: RestartScheduleResponse | null | undefined
  isLoading?: boolean
  className?: string
}

export const ServerRestartScheduleCard: React.FC<ServerRestartScheduleCardProps> = ({
  restartSchedule,
  isLoading = false,
  className
}) => {
  const navigate = useNavigate()

  const handleNavigateToCronManagement = () => {
    navigate('/cron', { state: { highlightJobId: restartSchedule?.cronjob_id } })
  }

  if (isLoading) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4" />
              重启计划
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <Spinner className="size-6" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!restartSchedule) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4" />
              重启计划
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Alert>
            <AlertTitle>未配置重启计划</AlertTitle>
            <AlertDescription>
              <div className="flex items-center justify-between">
                <span>此服务器尚未配置自动重启计划</span>
                <Button size="sm" variant="outline" onClick={handleNavigateToCronManagement}>
                  配置计划
                </Button>
              </div>
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="text-base">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4" />
            重启计划
          </div>
        </CardTitle>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleNavigateToCronManagement}
                >
                  <Settings className="mr-1 h-3.5 w-3.5" />
                  管理
                </Button>
              }
            />
            <TooltipContent>定时任务管理</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </CardHeader>
      <CardContent>
        <div className="space-y-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">状态:</span>
            <CronJobStatusTag status={restartSchedule.status} />
          </div>

          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">重启时间:</span>
            <span className="font-medium">{restartSchedule.scheduled_time}</span>
          </div>

          <div className="flex items-start justify-between">
            <span className="text-muted-foreground">Cron 表达式:</span>
            <div className="flex-1 ml-2">
              <CronExpressionDisplay
                cronExpression={restartSchedule.cron}
                size="small"
                showTooltip={true}
              />
            </div>
          </div>

          {restartSchedule.next_run_time && (
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">下次执行:</span>
              <span className="text-sm text-blue-600">{restartSchedule.next_run_time}</span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export default ServerRestartScheduleCard
