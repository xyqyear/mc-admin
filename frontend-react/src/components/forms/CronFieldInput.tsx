import React, { useState, useEffect } from 'react'
import { Select, Input, Space, InputNumber } from 'antd'

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
  disabled = false
}) => {
  const [mode, setMode] = useState<'any' | 'specific' | 'range' | 'interval' | 'list' | 'raw'>('any')
  const [specificValue, setSpecificValue] = useState<number>(config.min)
  const [rangeStart, setRangeStart] = useState<number>(config.min)
  const [rangeEnd, setRangeEnd] = useState<number>(config.max)
  const [intervalStep, setIntervalStep] = useState<number>(1)
  const [intervalStart, setIntervalStart] = useState<number>(config.min)
  const [listValues, setListValues] = useState<number[]>([])
  const [rawValue, setRawValue] = useState<string>('')

  // 解析当前值并设置模式
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

  // 根据模式生成值
  const generateValue = (newMode: string, params?: any) => {
    switch (newMode) {
      case 'any':
        return '*'
      case 'specific':
        return String(params?.value || specificValue)
      case 'range':
        return `${params?.start || rangeStart}-${params?.end || rangeEnd}`
      case 'interval':
        {
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

  const handleModeChange = (newMode: string) => {
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

  const modeOptions = [
    { label: '任意值 (*)', value: 'any' },
    { label: '指定值', value: 'specific' },
    { label: '范围', value: 'range' },
    { label: '间隔', value: 'interval' },
    { label: '列表', value: 'list' },
    { label: '自定义', value: 'raw' }
  ]

  return (
    <div className="space-y-3">
      <div>
        <div className="text-sm font-medium mb-2">{config.label}</div>
        <Select
          value={mode}
          onChange={handleModeChange}
          disabled={disabled}
          style={{ width: 140 }}
          options={modeOptions}
        />
      </div>

      {mode === 'specific' && (
        <div className="ml-6">
          {config.options ? (
            <Select
              value={specificValue}
              onChange={(val) => handleValueChange('specific', val)}
              disabled={disabled}
              style={{ width: 120 }}
              options={config.options}
            />
          ) : (
            <InputNumber
              value={specificValue}
              onChange={(val) => handleValueChange('specific', val || config.min)}
              min={config.min}
              max={config.max}
              disabled={disabled}
              style={{ width: 120 }}
            />
          )}
        </div>
      )}

      {mode === 'range' && (
        <div className="ml-6">
          <Space>
            <span>从</span>
            <InputNumber
              value={rangeStart}
              onChange={(val) => handleValueChange('rangeStart', val || config.min)}
              min={config.min}
              max={config.max}
              disabled={disabled}
              style={{ width: 80 }}
            />
            <span>到</span>
            <InputNumber
              value={rangeEnd}
              onChange={(val) => handleValueChange('rangeEnd', val || config.max)}
              min={config.min}
              max={config.max}
              disabled={disabled}
              style={{ width: 80 }}
            />
          </Space>
        </div>
      )}

      {mode === 'interval' && (
        <div className="ml-6">
          <Space>
            <span>从</span>
            <Select
              value={intervalStart}
              onChange={(val) => handleValueChange('intervalStart', val)}
              disabled={disabled}
              style={{ width: 100 }}
              options={[
                { label: '任意', value: config.min },
                ...Array.from({ length: config.max - config.min + 1 }, (_, i) => ({
                  label: String(config.min + i),
                  value: config.min + i
                }))
              ]}
            />
            <span>开始，每</span>
            <InputNumber
              value={intervalStep}
              onChange={(val) => handleValueChange('intervalStep', val || 1)}
              min={1}
              max={config.max - config.min}
              disabled={disabled}
              style={{ width: 80 }}
            />
            <span>个单位</span>
          </Space>
        </div>
      )}

      {mode === 'list' && (
        <div className="ml-6">
          <Select
            mode="multiple"
            value={listValues}
            onChange={(vals) => handleValueChange('list', vals)}
            disabled={disabled}
            style={{ width: 200 }}
            placeholder="选择多个值"
            options={Array.from({ length: config.max - config.min + 1 }, (_, i) => ({
              label: String(config.min + i),
              value: config.min + i
            }))}
          />
        </div>
      )}

      {mode === 'raw' && (
        <div className="ml-6">
          <Input
            value={rawValue}
            onChange={(e) => handleValueChange('raw', e.target.value)}
            disabled={disabled}
            placeholder="输入自定义表达式"
            style={{ width: 200 }}
          />
        </div>
      )}

      {config.specialValues && config.specialValues.length > 0 && (
        <div className="ml-6">
          <div className="text-xs text-gray-500">
            特殊值: {config.specialValues.map(sv => `${sv.label}(${sv.value})`).join(', ')}
          </div>
        </div>
      )}

      <div className="text-xs text-gray-500">
        当前值: <code className="bg-gray-100 px-1 rounded">{value}</code>
      </div>
    </div>
  )
}

export default CronFieldInput