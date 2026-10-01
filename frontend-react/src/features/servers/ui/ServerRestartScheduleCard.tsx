import { CronRegistrationStatus } from '@/features/schedules/ui/CronRegistrationStatus'
import React from 'react'
import { useNavigate } from 'react-router'
import { Clock, Settings } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/shared/ui/card'
import { Button } from '@/shared/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/shared/ui/alert'
import { Spinner } from '@/shared/ui/spinner'
import CronExpressionDisplay from '@/features/schedules/ui/CronExpressionDisplay'
import type { RestartScheduleResponse } from '@/features/servers/contracts';
import { CronJobStatusTag } from '@/features/schedules/ui/index'
import { useServerMutations } from '@/features/servers/commands'
import { useConfirm } from '@/shared/hooks/useConfirm'

interface ServerRestartScheduleCardProps {
  serverId: string
  restartSchedule: RestartScheduleResponse | null | undefined
  isLoading?: boolean
  error?: Error | null
  className?: string
}

export const ServerRestartScheduleCard: React.FC<ServerRestartScheduleCardProps> = ({
  serverId,
  restartSchedule,
  isLoading = false,
  error,
  className
}) => {
  const navigate = useNavigate()
  const createSchedule = useServerMutations().useCreateOrUpdateRestartSchedule()
  const { confirm, confirmDialog } = useConfirm()

  const handleNavigateToCronManagement = () => {
    navigate(`/cron?job=${encodeURIComponent(restartSchedule!.cronjob_id)}`)
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
          <Alert variant={error ? 'destructive' : 'default'}>
            <AlertTitle>{error ? '无法读取重启计划' : '未配置重启计划'}</AlertTitle>
            <AlertDescription>
              <div className="flex items-center justify-between">
                <span>{error?.message ?? '此服务器尚未配置自动重启计划'}</span>
                <Button size="sm" variant="outline" disabled={!!error || createSchedule.isPending} onClick={() => confirm({
                  title: '配置自动重启',
                  description: `为服务器“${serverId}”分配每日重启时间。创建后可在定时任务中调整时间或暂停计划。`,
                  confirmText: '创建重启计划',
                  onConfirm: async () => { await createSchedule.mutateAsync({ serverId }) },
                })}>
                  配置计划
                </Button>
              </div>
            </AlertDescription>
          </Alert>
        </CardContent>
        {confirmDialog}
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
        <Button
          size="sm"
          variant="outline"
          onClick={handleNavigateToCronManagement}
          title="定时任务管理"
        >
          <Settings className="mr-1 h-3.5 w-3.5" />
          管理
        </Button>
      </CardHeader>
      <CardContent>
        <div className="space-y-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">状态:</span>
            <CronJobStatusTag status={restartSchedule.status} />
          </div>

          <CronRegistrationStatus status={restartSchedule.registration_status} error={restartSchedule.registration_error} />

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

          {restartSchedule.next_run_time && (!restartSchedule.registration_status || restartSchedule.registration_status === 'registered') && (
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
