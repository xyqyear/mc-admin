import React from 'react'
import { Card, Progress } from 'antd'

interface ProgressMetricCardProps {
  value: number
  title: string
  extraInfo?: string
}

const ProgressMetricCard: React.FC<ProgressMetricCardProps> = ({
  value,
  title,
  extraInfo
}) => {
  const getProgressColor = (percentage: number) => {
    if (percentage >= 90) return '#f5222d'
    if (percentage >= 80) return '#fa8c16'
    if (percentage >= 60) return '#52c41a'
    if (percentage >= 40) return '#1890ff'
    return '#722ed1'
  }

  return (
    <Card
      className="h-full w-full"
      styles={{
        body: {
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          padding: '12px'
        }
      }}
    >
      <div className="flex-1 flex items-center justify-center mb-3">
        <Progress
          type="dashboard"
          percent={Number(value.toFixed(2))}
          strokeColor={getProgressColor(value)}
          format={(percent) => `${percent}%`}
          size={140}
        />
      </div>
      <div className="w-full">
        <div className="text-sm font-semibold text-gray-800 mb-2">
          {title}
        </div>
        {extraInfo && (
          <div
            className="text-xs text-gray-500 leading-tight px-1"
            title={extraInfo}
            style={{
              wordBreak: 'break-all',
              lineHeight: '1.2'
            }}
          >
            {extraInfo}
          </div>
        )}
      </div>
    </Card>
  )
}

export default ProgressMetricCard