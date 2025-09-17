import React from 'react'
import { Typography, Tooltip, Tag } from 'antd'

const { Text } = Typography

interface CronExpressionDisplayProps {
  cronExpression: string
  second?: string
  size?: 'small' | 'default'
  showTooltip?: boolean
}

const CronExpressionDisplay: React.FC<CronExpressionDisplayProps> = ({
  cronExpression,
  second,
  size = 'default',
  showTooltip = true
}) => {
  // 解析单个字段
  const parseField = (value: string, type: 'minute' | 'hour' | 'day' | 'month' | 'dayOfWeek' | 'second') => {
    if (value === '*') return '任意'
    if (value === '?') return '忽略'

    const ranges = {
      minute: { min: 0, max: 59, name: '分钟' },
      hour: { min: 0, max: 23, name: '小时' },
      day: { min: 1, max: 31, name: '日' },
      month: { min: 1, max: 12, name: '月' },
      dayOfWeek: { min: 0, max: 7, name: '周' },
      second: { min: 0, max: 59, name: '秒' }
    }

    const range = ranges[type]
    const monthNames = ['', '1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
    const dayNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六', '周日'] // 0和7都是周日

    // 处理步长值 (*/n 或 start/step)
    if (value.includes('/')) {
      const [rangeOrStar, step] = value.split('/')
      if (rangeOrStar === '*') {
        return `每${step}${range.name}`
      } else if (rangeOrStar.includes('-')) {
        const [start, end] = rangeOrStar.split('-')
        return `从${start}到${end}每${step}${range.name}`
      } else {
        return `从${rangeOrStar}开始每${step}${range.name}`
      }
    }

    // 处理范围 (n-m)
    if (value.includes('-')) {
      const [start, end] = value.split('-')
      if (type === 'month') {
        return `${monthNames[parseInt(start)]}-${monthNames[parseInt(end)]}`
      } else if (type === 'dayOfWeek') {
        return `${dayNames[parseInt(start)]}-${dayNames[parseInt(end)]}`
      }
      return `${start}-${end}${range.name}`
    }

    // 处理随机范围 (n~m)
    if (value.includes('~')) {
      const [start, end] = value.split('~')
      const startVal = start || range.min
      const endVal = end || range.max
      return `随机${startVal}-${endVal}${range.name}`
    }

    // 处理列表 (n,m,...)
    if (value.includes(',')) {
      const values = value.split(',')
      if (type === 'month') {
        return values.map(v => monthNames[parseInt(v)] || v).join('、')
      } else if (type === 'dayOfWeek') {
        return values.map(v => dayNames[parseInt(v)] || v).join('、')
      }
      return values.join('、') + range.name
    }

    // 单个值
    if (type === 'month') {
      return monthNames[parseInt(value)] || value + '月'
    } else if (type === 'dayOfWeek') {
      return dayNames[parseInt(value)] || value
    }

    return value + range.name
  }

  // 解析 cron 表达式为人类可读的描述
  const parseCronExpression = (cron: string, secondField?: string) => {
    try {
      const cronParts = cron.trim().split(/\s+/)
      if (cronParts.length !== 5) {
        return '无效的 cron 表达式'
      }

      const [minute, hour, day, month, dayOfWeek] = cronParts
      const sec = secondField || '0'

      // 构建自然语言描述
      let frequency = ''
      let timeDesc = ''
      let dateDesc = ''

      // 分析频率
      if (minute === '*' && hour === '*' && day === '*' && month === '*' && dayOfWeek === '*') {
        frequency = '每分钟'
      } else if (hour === '*' && day === '*' && month === '*' && dayOfWeek === '*') {
        if (minute.includes('/')) {
          const step = minute.split('/')[1]
          frequency = `每${step}分钟`
        } else if (minute === '0') {
          frequency = '每小时整点'
        } else {
          frequency = `每小时的${parseField(minute, 'minute')}`
        }
      } else if (day === '*' && month === '*' && dayOfWeek === '*') {
        if (hour.includes('/')) {
          const step = hour.split('/')[1]
          frequency = `每${step}小时`
        } else {
          frequency = '每天'
        }
        timeDesc = `${parseField(hour, 'hour')}${parseField(minute, 'minute')}`
      } else {
        frequency = '按计划'

        // 时间描述
        if (hour !== '*' || minute !== '*') {
          timeDesc = `${parseField(hour, 'hour')}${parseField(minute, 'minute')}`
        }

        // 日期描述
        const dayPart = day !== '*' ? parseField(day, 'day') : ''
        const monthPart = month !== '*' ? parseField(month, 'month') : ''
        const dayOfWeekPart = dayOfWeek !== '*' && dayOfWeek !== '?' ? parseField(dayOfWeek, 'dayOfWeek') : ''

        if (dayPart && dayOfWeekPart) {
          // 如果同时指定了日期和星期，按照cron规范，满足任一条件就执行
          dateDesc = `每月${dayPart}或每周${dayOfWeekPart}`
        } else if (dayPart) {
          dateDesc = `每月${dayPart}`
        } else if (dayOfWeekPart) {
          dateDesc = `每周${dayOfWeekPart}`
        }

        if (monthPart) {
          dateDesc = monthPart + (dateDesc ? '的' + dateDesc : '')
        }
      }

      // 秒字段描述
      let secDesc = ''
      if (sec !== '0' && sec !== '*' && secondField) {
        secDesc = `第${parseField(sec, 'second')}`
      }

      // 组合描述
      const descriptionParts = [frequency, dateDesc, timeDesc, secDesc].filter(Boolean)
      return descriptionParts.join(' ') || '自定义计划'

    } catch {
      return '无法解析表达式'
    }
  }

  const fullExpression = second ? `${second} ${cronExpression}` : cronExpression
  const humanReadable = parseCronExpression(cronExpression, second)

  const content = (
    <div className="flex items-center gap-2">
      <Tag className={`font-mono ${size === 'small' ? 'text-xs' : ''}`}>
        {fullExpression}
      </Tag>
      {showTooltip && (
        <Text type="secondary" className={size === 'small' ? 'text-xs' : 'text-sm'}>
          {humanReadable}
        </Text>
      )}
    </div>
  )

  if (!showTooltip) {
    return content
  }

  return (
    <Tooltip
      title={
        <div className="space-y-2">
          <div>
            <strong>Cron 表达式:</strong> {fullExpression}
          </div>
          <div>
            <strong>执行计划:</strong> {humanReadable}
          </div>
          <div className="text-xs text-gray-300">
            格式: {second ? '秒 ' : ''}分 时 日 月 周
          </div>
        </div>
      }
      placement="top"
    >
      <div className="cursor-help">
        {content}
      </div>
    </Tooltip>
  )
}

export default CronExpressionDisplay