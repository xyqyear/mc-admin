import React, { useState, useEffect } from 'react'
import { Clock } from 'lucide-react'
import { formatDateTime } from '@/utils/formatUtils'

interface NextRunTimeDisplayProps {
  nextRunTime: string | null
  className?: string
}

const NextRunTimeDisplay: React.FC<NextRunTimeDisplayProps> = ({
  nextRunTime,
  className = '',
}) => {
  const [timeLeft, setTimeLeft] = useState<string>('')

  useEffect(() => {
    if (!nextRunTime) {
      setTimeLeft('')
      return
    }

    const calculateTimeLeft = () => {
      const now = new Date().getTime()
      const targetTime = new Date(nextRunTime).getTime()
      const difference = targetTime - now

      if (difference <= 0) {
        setTimeLeft('即将执行')
        return
      }

      const days = Math.floor(difference / (1000 * 60 * 60 * 24))
      const hours = Math.floor((difference % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
      const minutes = Math.floor((difference % (1000 * 60 * 60)) / (1000 * 60))
      const seconds = Math.floor((difference % (1000 * 60)) / 1000)

      let result = ''
      if (days > 0) {
        result += `${days}天 `
      }
      if (hours > 0) {
        result += `${hours}小时 `
      }
      if (minutes > 0) {
        result += `${minutes}分钟 `
      }
      if (days === 0 && hours === 0) {
        result += `${seconds}秒`
      }

      setTimeLeft(result.trim() || '少于1秒')
    }

    calculateTimeLeft()
    const interval = setInterval(calculateTimeLeft, 1000)

    return () => clearInterval(interval)
  }, [nextRunTime])

  if (!nextRunTime) {
    return (
      <span className={`text-muted-foreground ${className}`}>
        <Clock className="mr-1 inline h-3.5 w-3.5" />
        无计划运行
      </span>
    )
  }

  const formattedTime = formatDateTime(nextRunTime)

  return (
    <span
      className={`font-mono ${className}`}
      title={`下次运行时间: ${formattedTime}`}
    >
      <Clock className="mr-1 inline h-3.5 w-3.5 text-blue-500" />
      {timeLeft}
    </span>
  )
}

export default NextRunTimeDisplay
