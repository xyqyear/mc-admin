import React, { useState, useEffect } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import CronFieldInput from './CronFieldInput'

interface CronExpressionBuilderProps {
  cronValue: string
  secondValue?: string
  onCronChange: (cron: string) => void
  onSecondChange?: (second: string) => void
  disabled?: boolean
}

const cronFieldConfigs = {
  second: {
    label: '秒 (0-59)',
    min: 0,
    max: 59,
  },
  minute: {
    label: '分钟 (0-59)',
    min: 0,
    max: 59,
  },
  hour: {
    label: '小时 (0-23)',
    min: 0,
    max: 23,
  },
  dayOfMonth: {
    label: '日期 (1-31)',
    min: 1,
    max: 31,
    specialValues: [
      { label: '最后一天', value: 'L' },
      { label: '工作日', value: 'W' },
    ],
  },
  month: {
    label: '月份 (1-12)',
    min: 1,
    max: 12,
    options: [
      { label: '1月', value: 1 }, { label: '2月', value: 2 }, { label: '3月', value: 3 },
      { label: '4月', value: 4 }, { label: '5月', value: 5 }, { label: '6月', value: 6 },
      { label: '7月', value: 7 }, { label: '8月', value: 8 }, { label: '9月', value: 9 },
      { label: '10月', value: 10 }, { label: '11月', value: 11 }, { label: '12月', value: 12 },
    ],
  },
  dayOfWeek: {
    label: '星期 (0-7)',
    min: 0,
    max: 7,
    options: [
      { label: '周日', value: 0 }, { label: '周一', value: 1 }, { label: '周二', value: 2 },
      { label: '周三', value: 3 }, { label: '周四', value: 4 }, { label: '周五', value: 5 },
      { label: '周六', value: 6 }, { label: '周日', value: 7 },
    ],
    specialValues: [
      { label: '最后一个', value: 'L' },
    ],
  },
}

const presets = [
  { label: '每分钟', cron: '* * * * *' },
  { label: '每小时', cron: '0 * * * *' },
  { label: '每天午夜', cron: '0 0 * * *' },
  { label: '每天上午9点', cron: '0 9 * * *' },
  { label: '每周日午夜', cron: '0 0 * * 0' },
  { label: '每月1号午夜', cron: '0 0 1 * *' },
  { label: '工作日上午9点', cron: '0 9 * * 1-5' },
  { label: '每6小时', cron: '0 */6 * * *' },
  { label: '每30分钟', cron: '*/30 * * * *' },
]

const CronExpressionBuilder: React.FC<CronExpressionBuilderProps> = ({
  cronValue,
  secondValue = '',
  onCronChange,
  onSecondChange,
  disabled = false,
}) => {
  const [mode, setMode] = useState<'visual' | 'raw'>('visual')
  const [cronFields, setCronFields] = useState({
    minute: '*',
    hour: '*',
    dayOfMonth: '*',
    month: '*',
    dayOfWeek: '*',
  })
  const [second, setSecond] = useState(secondValue)
  const [rawCron, setRawCron] = useState(cronValue)

  useEffect(() => {
    if (cronValue) {
      const parts = cronValue.trim().split(/\s+/)
      if (parts.length === 5) {
        setCronFields({
          minute: parts[0] || '*',
          hour: parts[1] || '*',
          dayOfMonth: parts[2] || '*',
          month: parts[3] || '*',
          dayOfWeek: parts[4] || '*',
        })
      }
      setRawCron(cronValue)
    }
  }, [cronValue])

  useEffect(() => {
    setSecond(secondValue || '')
  }, [secondValue])

  const generateCronExpression = (fields: typeof cronFields) => {
    return `${fields.minute} ${fields.hour} ${fields.dayOfMonth} ${fields.month} ${fields.dayOfWeek}`
  }

  const handleModeChange = (value: string | null) => {
    if (value) setMode(value as any)
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
          dayOfWeek: parts[4],
        })
      }
    }
  }

  const currentExpression = mode === 'visual' ? generateCronExpression(cronFields) : rawCron

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">配置模式：</span>
        <Select
          value={mode}
          onValueChange={handleModeChange}
          disabled={disabled}
          itemToStringLabel={(v) => v === 'visual' ? '可视化配置' : '原始表达式'}
        >
          <SelectTrigger className="w-35">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="visual">可视化配置</SelectItem>
            <SelectItem value="raw">原始表达式</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">常用预设</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-2">
            {presets.map((preset, index) => (
              <button
                key={index}
                className="text-left p-2 text-sm border rounded hover:bg-accent hover:border-primary/30 disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={() => handlePresetSelect(preset.cron)}
                disabled={disabled}
              >
                <div className="font-medium">{preset.label}</div>
                <div className="text-xs text-muted-foreground">{preset.cron}</div>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {mode === 'visual' ? (
        <div className="space-y-4">
          {onSecondChange && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">秒字段 (可选)</CardTitle>
              </CardHeader>
              <CardContent>
                <CronFieldInput
                  value={second}
                  onChange={handleSecondChange}
                  config={cronFieldConfigs.second}
                  disabled={disabled}
                />
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Cron表达式字段</CardTitle>
            </CardHeader>
            <CardContent>
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
            </CardContent>
          </Card>
        </div>
      ) : (
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">
                Cron表达式
                <span className="text-xs text-muted-foreground font-normal ml-2">(分 时 日 月 周)</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Input
                value={rawCron}
                onChange={(e) => handleRawCronChange(e.target.value)}
                placeholder="输入Cron表达式，例如: 0 0 * * *"
                disabled={disabled}
              />
              <div className="mt-2 text-xs text-muted-foreground">
                <div>格式说明: 分钟(0-59) 小时(0-23) 日期(1-31) 月份(1-12) 星期(1-7)</div>
                <div>特殊字符: * (任意) / (间隔) - (范围) , (列表) ? (忽略)</div>
              </div>
            </CardContent>
          </Card>

          {onSecondChange && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">秒字段 (可选)</CardTitle>
              </CardHeader>
              <CardContent>
                <Input
                  value={second}
                  onChange={(e) => handleSecondChange(e.target.value)}
                  placeholder="输入秒字段，例如: 30"
                  disabled={disabled}
                />
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {mode === 'visual' && (
        <Alert>
          <AlertTitle>表达式预览</AlertTitle>
          <AlertDescription>
            <div className="space-y-1">
              <div>
                <strong>Cron表达式:</strong> <code className="bg-muted px-1 rounded">{currentExpression}</code>
              </div>
              {second && (
                <div>
                  <strong>秒字段:</strong> <code className="bg-muted px-1 rounded">{second}</code>
                </div>
              )}
            </div>
          </AlertDescription>
        </Alert>
      )}
    </div>
  )
}

export default CronExpressionBuilder
