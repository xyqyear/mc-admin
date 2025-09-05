import React from 'react'
import { Card } from 'antd'

interface SimpleMetricCardProps {
  value: number | string
  title: string
}

const SimpleMetricCard: React.FC<SimpleMetricCardProps> = ({ value, title }) => {
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
          textAlign: 'center'
        }
      }}
    >
      <div>
        <div className="text-3xl sm:text-4xl font-bold text-gray-800 mb-3">
          {value}
        </div>
        <div className="text-sm sm:text-base font-semibold text-gray-600">
          {title}
        </div>
      </div>
    </Card>
  )
}

export default SimpleMetricCard