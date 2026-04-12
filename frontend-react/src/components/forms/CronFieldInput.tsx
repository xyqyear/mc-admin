import React, { useState, useEffect } from 'react'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'

interface CronFieldConfig {
  label: string
  min: number
  max: number
  options?: { label: string; value: number }[]
  specialValues?: { label: string; value: string }[]
}

interface CronFieldInputProps {
  value: string
  onChange: (value: string) => void
  config: CronFieldConfig
  disabled?: boolean
}

const CronFieldInput: React.FC<CronFieldInputProps> = ({
  value,
  onChange,
  config,
  disabled = false,
}) => {
  const [mode, setMode] = useState<'any' | 'specific' | 'range' | 'interval' | 'list' | 'raw'>('any')
  const [specificValue, setSpecificValue] = useState<number>(config.min)
  const [rangeStart, setRangeStart] = useState<number>(config.min)
  const [rangeEnd, setRangeEnd] = useState<number>(config.max)
  const [intervalStep, setIntervalStep] = useState<number>(1)
  const [intervalStart, setIntervalStart] = useState<number>(config.min)
  const [listValues, setListValues] = useState<number[]>([])
  const [rawValue, setRawValue] = useState<string>('')

  useEffect(() => {
    if (value === '*') {
      setMode('any')
    } else if (value.includes('/')) {
      setMode('interval')
      const [start, step] = value.split('/')
      setIntervalStart(start === '*' ? config.min : parseInt(start))
      setIntervalStep(parseInt(step))
    } else if (value.includes('-')) {
      setMode('range')
      const [start, end] = value.split('-')
      setRangeStart(parseInt(start))
      setRangeEnd(parseInt(end))
    } else if (value.includes(',')) {
      setMode('list')
      setListValues(value.split(',').map(v => parseInt(v.trim())))
    } else if (!isNaN(parseInt(value))) {
      setMode('specific')
      setSpecificValue(parseInt(value))
    } else {
      setMode('raw')
      setRawValue(value)
    }
  }, [value, config.min, config.max])

  const generateValue = (newMode: string, params?: any) => {
    switch (newMode) {
      case 'any':
        return '*'
      case 'specific':
        return String(params?.value || specificValue)
      case 'range':
        return `${params?.start || rangeStart}-${params?.end || rangeEnd}`
      case 'interval': {
        const start = params?.start || intervalStart
        const step = params?.step || intervalStep
        return start === config.min ? `*/${step}` : `${start}/${step}`
      }
      case 'list':
        return (params?.values || listValues).join(',')
      case 'raw':
        return params?.raw || rawValue
      default:
        return '*'
    }
  }

  const handleModeChange = (newMode: string | null) => {
    if (!newMode) return
    setMode(newMode as any)
    onChange(generateValue(newMode))
  }

  const handleValueChange = (type: string, newValue: any) => {
    let newGeneratedValue = ''

    switch (type) {
      case 'specific':
        setSpecificValue(newValue)
        newGeneratedValue = generateValue('specific', { value: newValue })
        break
      case 'rangeStart':
        setRangeStart(newValue)
        newGeneratedValue = generateValue('range', { start: newValue, end: rangeEnd })
        break
      case 'rangeEnd':
        setRangeEnd(newValue)
        newGeneratedValue = generateValue('range', { start: rangeStart, end: newValue })
        break
      case 'intervalStart':
        setIntervalStart(newValue)
        newGeneratedValue = generateValue('interval', { start: newValue, step: intervalStep })
        break
      case 'intervalStep':
        setIntervalStep(newValue)
        newGeneratedValue = generateValue('interval', { start: intervalStart, step: newValue })
        break
      case 'list':
        setListValues(newValue)
        newGeneratedValue = generateValue('list', { values: newValue })
        break
      case 'raw':
        setRawValue(newValue)
        newGeneratedValue = generateValue('raw', { raw: newValue })
        break
    }

    onChange(newGeneratedValue)
  }

  const handleNumberInput = (type: string, inputValue: string, min: number, max: number) => {
    const num = parseInt(inputValue)
    if (!isNaN(num) && num >= min && num <= max) {
      handleValueChange(type, num)
    }
  }

  const toggleListValue = (val: number) => {
    const next = listValues.includes(val)
      ? listValues.filter(v => v !== val)
      : [...listValues, val].sort((a, b) => a - b)
    handleValueChange('list', next)
  }

  const allValues = Array.from({ length: config.max - config.min + 1 }, (_, i) => config.min + i)

  const modeLabels: Record<string, string> = {
    any: '任意值 (*)',
    specific: '指定值',
    range: '范围',
    interval: '间隔',
    list: '列表',
    raw: '自定义',
  }

  const optionLabelMap = config.options
    ? Object.fromEntries(config.options.map(o => [String(o.value), o.label]))
    : undefined

  return (
    <div className="space-y-3">
      <div>
        <div className="text-sm font-medium mb-2">{config.label}</div>
        <Select
          value={mode}
          onValueChange={handleModeChange}
          disabled={disabled}
          itemToStringLabel={(v) => modeLabels[v as string] || String(v)}
        >
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">任意值 (*)</SelectItem>
            <SelectItem value="specific">指定值</SelectItem>
            <SelectItem value="range">范围</SelectItem>
            <SelectItem value="interval">间隔</SelectItem>
            <SelectItem value="list">列表</SelectItem>
            <SelectItem value="raw">自定义</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {mode === 'specific' && (
        <div className="ml-6">
          {config.options ? (
            <Select
              value={String(specificValue)}
              onValueChange={(val) => val && handleValueChange('specific', parseInt(val))}
              disabled={disabled}
              itemToStringLabel={(v) => optionLabelMap?.[v as string] || String(v)}
            >
              <SelectTrigger className="w-30">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {config.options.map(opt => (
                  <SelectItem key={opt.value} value={String(opt.value)}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Input
              type="number"
              value={specificValue}
              onChange={(e) => handleNumberInput('specific', e.target.value, config.min, config.max)}
              min={config.min}
              max={config.max}
              disabled={disabled}
              className="w-30"
            />
          )}
        </div>
      )}

      {mode === 'range' && (
        <div className="ml-6 flex items-center gap-2">
          <span className="text-sm">从</span>
          <Input
            type="number"
            value={rangeStart}
            onChange={(e) => handleNumberInput('rangeStart', e.target.value, config.min, config.max)}
            min={config.min}
            max={config.max}
            disabled={disabled}
            className="w-20"
          />
          <span className="text-sm">到</span>
          <Input
            type="number"
            value={rangeEnd}
            onChange={(e) => handleNumberInput('rangeEnd', e.target.value, config.min, config.max)}
            min={config.min}
            max={config.max}
            disabled={disabled}
            className="w-20"
          />
        </div>
      )}

      {mode === 'interval' && (
        <div className="ml-6 flex items-center gap-2">
          <span className="text-sm">从</span>
          <Select
            value={String(intervalStart)}
            onValueChange={(val) => val && handleValueChange('intervalStart', parseInt(val))}
            disabled={disabled}
            itemToStringLabel={(v) => v === String(config.min) ? '任意' : String(v)}
          >
            <SelectTrigger className="w-25">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={String(config.min)}>任意</SelectItem>
              {allValues.map(v => (
                <SelectItem key={v} value={String(v)}>{v}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-sm">开始，每</span>
          <Input
            type="number"
            value={intervalStep}
            onChange={(e) => handleNumberInput('intervalStep', e.target.value, 1, config.max - config.min)}
            min={1}
            max={config.max - config.min}
            disabled={disabled}
            className="w-20"
          />
          <span className="text-sm">个单位</span>
        </div>
      )}

      {mode === 'list' && (
        <div className="ml-6 flex flex-wrap gap-1">
          {allValues.map(v => {
            const label = config.options?.find(o => o.value === v)?.label ?? String(v)
            const isSelected = listValues.includes(v)
            return (
              <Badge
                key={v}
                variant={isSelected ? 'default' : 'outline'}
                className="cursor-pointer select-none"
                onClick={() => !disabled && toggleListValue(v)}
              >
                {label}
              </Badge>
            )
          })}
        </div>
      )}

      {mode === 'raw' && (
        <div className="ml-6">
          <Input
            value={rawValue}
            onChange={(e) => handleValueChange('raw', e.target.value)}
            disabled={disabled}
            placeholder="输入自定义表达式"
            className="w-50"
          />
        </div>
      )}

      {config.specialValues && config.specialValues.length > 0 && (
        <div className="ml-6 text-xs text-muted-foreground">
          特殊值: {config.specialValues.map(sv => `${sv.label}(${sv.value})`).join(', ')}
        </div>
      )}

      <div className="text-xs text-muted-foreground">
        当前值: <code className="bg-muted px-1 rounded">{value}</code>
      </div>
    </div>
  )
}

export default CronFieldInput
