import React from 'react'
import { Card, Progress } from 'antd'

interface MetricCardProps {
  value: number
  title: string
  extraValues?: string
  isProgress?: boolean
}

const MetricCard: React.FC<MetricCardProps> = ({
  value,
  title,
  extraValues,
  isProgress = false,
}) => {
  const getProgressColor = (percentage: number) => {
    if (percentage >= 90) return '#f5222d'
    if (percentage >= 80) return '#fa8c16'
    if (percentage >= 60) return '#52c41a'
    if (percentage >= 40) return '#1890ff'
    return '#722ed1'
  }

  return (
    <Card className="flex-1 min-w-64">
      <div className="text-center">
        {isProgress ? (
          <div className="mb-4">
            <Progress
              type="dashboard"
              percent={Number(value.toFixed(2))}
              strokeColor={getProgressColor(value)}
              format={(percent) => `${percent}%`}
            />
          </div>
        ) : (
          <div className="h-36 flex items-center justify-center">
            <span className="text-3xl font-bold">{value}</span>
          </div>
        )}
        <div className="text-lg font-bold mb-1">{title}</div>
        {extraValues && (
          <div className="text-sm text-gray-500">{extraValues}</div>
        )}
      </div>
    </Card>
  )
}

export default MetricCard
