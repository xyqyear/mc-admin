import React from 'react'
import { Card, CardContent } from '@/components/ui/card'

interface SimpleMetricCardProps {
  value: number | string
  title: string
}

const SimpleMetricCard: React.FC<SimpleMetricCardProps> = ({ value, title }) => {
  return (
    <Card className="h-full w-full">
      <CardContent className="h-full flex flex-col items-center justify-center text-center">
        <div className="text-3xl sm:text-4xl font-bold text-foreground mb-3">
          {value}
        </div>
        <div className="text-sm sm:text-base font-semibold text-muted-foreground">
          {title}
        </div>
      </CardContent>
    </Card>
  )
}

export default SimpleMetricCard
