import React, { useState, useEffect } from 'react'
import { Select, Card, Input, Alert, Space } from 'antd'
import CronFieldInput from './CronFieldInput'

interface CronExpressionBuilderProps {
  cronValue: string
  secondValue?: string
  onCronChange: (cron: string) => void
  onSecondChange?: (second: string) => void
  disabled?: boolean
}

// Cron字段配置
const cronFieldConfigs = {
  second: {
    label: '秒 (0-59)',
    min: 0,
    max: 59
  },
  minute: {
    label: '分钟 (0-59)',
    min: 0,
    max: 59
  },
  hour: {
    label: '小时 (0-23)',
    min: 0,
    max: 23
  },
  dayOfMonth: {
    label: '日期 (1-31)',
    min: 1,
    max: 31,
    specialValues: [
      { label: '最后一天', value: 'L' },
      { label: '工作日', value: 'W' }
    ]
  },
  month: {
    label: '月份 (1-12)',
    min: 1,
    max: 12,
    options: [
      { label: '1月', value: 1 }, { label: '2月', value: 2 }, { label: '3月', value: 3 },
      { label: '4月', value: 4 }, { label: '5月', value: 5 }, { label: '6月', value: 6 },
      { label: '7月', value: 7 }, { label: '8月', value: 8 }, { label: '9月', value: 9 },
      { label: '10月', value: 10 }, { label: '11月', value: 11 }, { label: '12月', value: 12 }
    ]
  },
  dayOfWeek: {
    label: '星期 (0-7)',
    min: 0,
    max: 7,
    options: [
      { label: '周日', value: 0 }, { label: '周一', value: 1 }, { label: '周二', value: 2 },
      { label: '周三', value: 3 }, { label: '周四', value: 4 }, { label: '周五', value: 5 },
      { label: '周六', value: 6 }, { label: '周日', value: 7 }
    ],
    specialValues: [
      { label: '最后一个', value: 'L' }
    ]
  }
}

// 常用预设
const presets = [
  { label: '每分钟', cron: '* * * * *' },
  { label: '每小时', cron: '0 * * * *' },
  { label: '每天午夜', cron: '0 0 * * *' },
  { label: '每天上午9点', cron: '0 9 * * *' },
  { label: '每周日午夜', cron: '0 0 * * 0' },
  { label: '每月1号午夜', cron: '0 0 1 * *' },
  { label: '工作日上午9点', cron: '0 9 * * 1-5' },
  { label: '每6小时', cron: '0 */6 * * *' },
  { label: '每30分钟', cron: '*/30 * * * *' }
]

const CronExpressionBuilder: React.FC<CronExpressionBuilderProps> = ({
  cronValue,
  secondValue = '',
  onCronChange,
  onSecondChange,
  disabled = false
}) => {
  const [mode, setMode] = useState<'visual' | 'raw'>('visual')
  const [cronFields, setCronFields] = useState({
    minute: '*',
    hour: '*',
    dayOfMonth: '*',
    month: '*',
    dayOfWeek: '*'
  })
  const [second, setSecond] = useState(secondValue)
  const [rawCron, setRawCron] = useState(cronValue)

  // 解析Cron表达式
  useEffect(() => {
    if (cronValue) {
      const parts = cronValue.trim().split(/\s+/)
      if (parts.length === 5) {
        setCronFields({
          minute: parts[0] || '*',
          hour: parts[1] || '*',
          dayOfMonth: parts[2] || '*',
          month: parts[3] || '*',
          dayOfWeek: parts[4] || '*'
        })
      }
      setRawCron(cronValue)
    }
  }, [cronValue])

  useEffect(() => {
    setSecond(secondValue || '')
  }, [secondValue])

  // 生成Cron表达式
  const generateCronExpression = (fields: typeof cronFields) => {
    return `${fields.minute} ${fields.hour} ${fields.dayOfMonth} ${fields.month} ${fields.dayOfWeek}`
  }

  const handleModeChange = (value: string) => {
    setMode(value as any)
  }

  const handleFieldChange = (field: keyof typeof cronFields, value: string) => {
    const newFields = { ...cronFields, [field]: value }
    setCronFields(newFields)
    if (mode === 'visual') {
      onCronChange(generateCronExpression(newFields))
    }
  }

  const handleSecondChange = (value: string) => {
    setSecond(value)
    if (onSecondChange) {
      onSecondChange(value)
    }
  }

  const handleRawCronChange = (value: string) => {
    setRawCron(value)
    if (mode === 'raw') {
      onCronChange(value)
    }
  }

  const handlePresetSelect = (presetCron: string) => {
    onCronChange(presetCron)
    setRawCron(presetCron)
    if (mode === 'visual') {
      const parts = presetCron.split(/\s+/)
      if (parts.length === 5) {
        setCronFields({
          minute: parts[0],
          hour: parts[1],
          dayOfMonth: parts[2],
          month: parts[3],
          dayOfWeek: parts[4]
        })
      }
    }
  }

  const currentExpression = mode === 'visual' ? generateCronExpression(cronFields) : rawCron

  return (
    <div className="space-y-4">
      {/* 模式选择 */}
      <div>
        <Space>
          <span className="text-sm font-medium">配置模式：</span>
          <Select
            value={mode}
            onChange={handleModeChange}
            disabled={disabled}
            style={{ width: 140 }}
            options={[
              { label: '可视化配置', value: 'visual' },
              { label: '原始表达式', value: 'raw' }
            ]}
          />
        </Space>
      </div>

      {/* 常用预设 */}
      <Card size="small" title="常用预设" className="bg-gray-50">
        <div className="grid grid-cols-3 gap-2">
          {presets.map((preset, index) => (
            <button
              key={index}
              className="text-left p-2 text-sm border rounded hover:bg-blue-50 hover:border-blue-300 disabled:opacity-50 disabled:cursor-not-allowed"
              onClick={() => handlePresetSelect(preset.cron)}
              disabled={disabled}
            >
              <div className="font-medium">{preset.label}</div>
              <div className="text-xs text-gray-500">{preset.cron}</div>
            </button>
          ))}
        </div>
      </Card>

      {mode === 'visual' ? (
        <div className="space-y-4">
          {/* 秒字段 */}
          {onSecondChange && (
            <Card size="small" title="秒字段 (可选)">
              <CronFieldInput
                value={second}
                onChange={handleSecondChange}
                config={cronFieldConfigs.second}
                disabled={disabled}
              />
            </Card>
          )}

          {/* Cron字段 */}
          <Card size="small" title="Cron表达式字段">
            <div className="space-y-6">
              <CronFieldInput
                value={cronFields.minute}
                onChange={(value) => handleFieldChange('minute', value)}
                config={cronFieldConfigs.minute}
                disabled={disabled}
              />

              <CronFieldInput
                value={cronFields.hour}
                onChange={(value) => handleFieldChange('hour', value)}
                config={cronFieldConfigs.hour}
                disabled={disabled}
              />

              <CronFieldInput
                value={cronFields.dayOfMonth}
                onChange={(value) => handleFieldChange('dayOfMonth', value)}
                config={cronFieldConfigs.dayOfMonth}
                disabled={disabled}
              />

              <CronFieldInput
                value={cronFields.month}
                onChange={(value) => handleFieldChange('month', value)}
                config={cronFieldConfigs.month}
                disabled={disabled}
              />

              <CronFieldInput
                value={cronFields.dayOfWeek}
                onChange={(value) => handleFieldChange('dayOfWeek', value)}
                config={cronFieldConfigs.dayOfWeek}
                disabled={disabled}
              />
            </div>
          </Card>
        </div>
      ) : (
        <div className="space-y-4">
          {/* 原始表达式输入 */}
          <Card
            size="small"
            title={
              <Space>
                <span>Cron表达式</span>
                <span className="text-xs text-gray-500 font-normal">(分 时 日 月 周)</span>
              </Space>
            }
          >
            <Input
              value={rawCron}
              onChange={(e) => handleRawCronChange(e.target.value)}
              placeholder="输入Cron表达式，例如: 0 0 * * *"
              disabled={disabled}
            />
            <div className="mt-2 text-xs text-gray-500">
              <div>格式说明: 分钟(0-59) 小时(0-23) 日期(1-31) 月份(1-12) 星期(1-7)</div>
              <div>特殊字符: * (任意) / (间隔) - (范围) , (列表) ? (忽略)</div>
            </div>
          </Card>

          {/* 秒字段 */}
          {onSecondChange && (
            <Card size="small" title="秒字段 (可选)">
              <Input
                value={second}
                onChange={(e) => handleSecondChange(e.target.value)}
                placeholder="输入秒字段，例如: 30"
                disabled={disabled}
              />
            </Card>
          )}
        </div>
      )}

      {/* 表达式预览 - 仅在可视化模式下显示 */}
      {mode === 'visual' && (
        <Alert
          message="表达式预览"
          description={
            <div className="space-y-2">
              <div>
                <strong>Cron表达式:</strong> <code className="bg-gray-100 px-1 rounded">{currentExpression}</code>
              </div>
              {second && (
                <div>
                  <strong>秒字段:</strong> <code className="bg-gray-100 px-1 rounded">{second}</code>
                </div>
              )}
            </div>
          }
          type="info"
          showIcon
        />
      )}
    </div>
  )
}

export default CronExpressionBuilder