import React from 'react'
import { Typography } from 'antd'
import { useCronJobNextRunTime } from '@/hooks/queries/base/useCronQueries'
import NextRunTimeDisplay from './NextRunTimeDisplay'

const { Text } = Typography

interface NextRunTimeCellProps {
  cronjobId: string
  status: string
}

const NextRunTimeCell: React.FC<NextRunTimeCellProps> = ({
  cronjobId,
  status
}) => {
  const { data: nextRunData, isLoading } = useCronJobNextRunTime(
    status.toLowerCase() === 'active' ? cronjobId : null
  )

  if (status.toLowerCase() !== 'active') {
    return (
      <Text type="secondary" className="text-xs">
        -
      </Text>
    )
  }

  if (isLoading) {
    return (
      <Text type="secondary" className="text-xs">
        加载中...
      </Text>
    )
  }

  return (
    <NextRunTimeDisplay
      nextRunTime={nextRunData?.next_run_time || null}
    />
  )
}

export default NextRunTimeCell