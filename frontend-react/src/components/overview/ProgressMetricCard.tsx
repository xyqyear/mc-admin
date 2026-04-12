import React from 'react'
import { Card, CardContent } from '@/components/ui/card'

interface ProgressMetricCardProps {
  value: number
  title: string
  extraInfo?: string
}

const getProgressColor = (percentage: number) => {
  // Map 0-100% to hue 120 (green) → 60 (yellow) → 0 (red)
  const hue = Math.max(0, 120 - (percentage / 100) * 120)
  return `hsl(${hue}, 80%, 50%)`
}

const CircularProgress: React.FC<{ value: number; size?: number }> = ({
  value,
  size = 140,
}) => {
  const strokeWidth = 8
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  // Dashboard style: 3/4 circle (270 degrees)
  const dashTotal = circumference * 0.75
  const dashOffset = dashTotal - (dashTotal * Math.min(value, 100)) / 100
  // Rotate to start from bottom-left (135 degrees)
  const rotation = 135

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {/* Background track */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="currentColor"
        className="text-muted"
        strokeWidth={strokeWidth}
        strokeDasharray={`${dashTotal} ${circumference}`}
        strokeLinecap="round"
        transform={`rotate(${rotation} ${size / 2} ${size / 2})`}
      />
      {/* Progress arc */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={getProgressColor(value)}
        strokeWidth={strokeWidth}
        strokeDasharray={`${dashTotal} ${circumference}`}
        strokeDashoffset={dashOffset}
        strokeLinecap="round"
        transform={`rotate(${rotation} ${size / 2} ${size / 2})`}
        className="transition-all duration-300"
      />
      {/* Center text */}
      <text
        x={size / 2}
        y={size / 2}
        textAnchor="middle"
        dominantBaseline="central"
        className="fill-foreground text-2xl font-semibold"
        fontSize="24"
      >
        {value.toFixed(2)}%
      </text>
    </svg>
  )
}

const ProgressMetricCard: React.FC<ProgressMetricCardProps> = ({
  value,
  title,
  extraInfo,
}) => {
  return (
    <Card className="h-full w-full">
      <CardContent className="h-full flex flex-col items-center justify-center text-center p-3">
        <div className="flex-1 flex items-center justify-center mb-3">
          <CircularProgress value={value} />
        </div>
        <div className="w-full">
          <div className="text-sm font-semibold text-foreground mb-2">
            {title}
          </div>
          {extraInfo && (
            <div
              className="text-xs text-muted-foreground leading-tight px-1 break-all"
              title={extraInfo}
            >
              {extraInfo}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export default ProgressMetricCard
