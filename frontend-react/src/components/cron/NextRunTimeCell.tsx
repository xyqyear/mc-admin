import React from 'react'
import { useCronJobNextRunTime } from '@/hooks/queries/base/useCronQueries'
import NextRunTimeDisplay from './NextRunTimeDisplay'

interface NextRunTimeCellProps {
  cronjobId: string
  status: string
}

const NextRunTimeCell: React.FC<NextRunTimeCellProps> = ({
  cronjobId,
  status,
}) => {
  const { data: nextRunData, isLoading } = useCronJobNextRunTime(
    status.toLowerCase() === 'active' ? cronjobId : null
  )

  if (status.toLowerCase() !== 'active') {
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
