import React, { useState, useEffect } from 'react'
import { Typography, Tooltip } from 'antd'
import { ClockCircleOutlined } from '@ant-design/icons'
import { formatDateTime } from '@/utils/formatUtils'

const { Text } = Typography

interface NextRunTimeDisplayProps {
  nextRunTime: string | null
  className?: string
}

const NextRunTimeDisplay: React.FC<NextRunTimeDisplayProps> = ({
  nextRunTime,
  className = ''
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
      <Text type="secondary" className={className}>
        <ClockCircleOutlined className="mr-1" />
        无计划运行
      </Text>
    )
  }

  const formattedTime = formatDateTime(nextRunTime)

  return (
    <Tooltip title={`下次运行时间: ${formattedTime}`}>
      <Text className={`${className} font-mono`}>
        <ClockCircleOutlined className="mr-1 text-blue-500" />
        {timeLeft}
      </Text>
    </Tooltip>
  )
}

export default NextRunTimeDisplay