import type { RegistrationStatus } from '@/features/schedules/contracts'
import React from 'react'
import { useCronJobNextRunTime } from '@/features/schedules/queries'
import NextRunTimeDisplay from '@/features/schedules/ui/NextRunTimeDisplay'

interface NextRunTimeCellProps {
  cronjobId: string
  status: string
  registrationStatus?: RegistrationStatus
}

const NextRunTimeCell: React.FC<NextRunTimeCellProps> = ({
  cronjobId,
  status,
  registrationStatus,
}) => {
  const registered = !registrationStatus || registrationStatus === 'registered'
  const { data: nextRunData, isLoading } = useCronJobNextRunTime(
    status.toLowerCase() === 'active' && registered ? cronjobId : null
  )

  if (status.toLowerCase() !== 'active' || !registered) {
    return <span className="text-xs text-muted-foreground">-</span>
  }

  if (isLoading) {
    return <span className="text-xs text-muted-foreground">加载中...</span>
  }

  return (
    <NextRunTimeDisplay nextRunTime={nextRunData?.next_run_time || null} />
  )
}

export default NextRunTimeCell
