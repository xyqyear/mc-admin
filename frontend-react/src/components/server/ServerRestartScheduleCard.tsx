import React from 'react'
import { Card, Button, Space, Alert, Tooltip } from 'antd'
import { ClockCircleOutlined, SettingOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
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

  if (!restartSchedule) {
    return (
      <Card
        title={
          <Space>
            <ClockCircleOutlined />
            重启计划
          </Space>
        }
        className={className}
        size="small"
        loading={isLoading}
      >
        <Alert
          message="未配置重启计划"
          description="此服务器尚未配置自动重启计划"
          type="info"
          showIcon
          action={
            <Button size="small" onClick={handleNavigateToCronManagement}>
              配置计划
            </Button>
          }
        />
      </Card>
    )
  }

  return (
    <Card
      title={
        <Space>
          <ClockCircleOutlined />
          重启计划
        </Space>
      }
      className={className}
      size="small"
      loading={isLoading}
      extra={
        <Space>
          <Tooltip title="定时任务管理">
            <Button
              size="small"
              icon={<SettingOutlined />}
              onClick={handleNavigateToCronManagement}
            >
              管理
            </Button>
          </Tooltip>
        </Space>
      }
    >
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-gray-600">状态:</span>
          <CronJobStatusTag status={restartSchedule.status} />
        </div>

        <div className="flex items-center justify-between">
          <span className="text-gray-600">重启时间:</span>
          <span className="font-medium">{restartSchedule.scheduled_time}</span>
        </div>

        <div className="flex items-start justify-between">
          <span className="text-gray-600">Cron 表达式:</span>
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
            <span className="text-gray-600">下次执行:</span>
            <span className="text-sm text-blue-600">{restartSchedule.next_run_time}</span>
          </div>
        )}
      </div>
    </Card>
  )
}

export default ServerRestartScheduleCard