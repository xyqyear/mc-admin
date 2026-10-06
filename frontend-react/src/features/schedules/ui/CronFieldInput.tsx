import React, { useState, useEffect } from 'react'
import { Input } from '@/shared/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/ui/select'
import { Badge } from '@/shared/ui/badge'

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

type CronFieldMode = 'any' | 'specific' | 'range' | 'interval' | 'list' | 'raw'
type NumericFieldChange = 'specific' | 'rangeStart' | 'rangeEnd' | 'intervalStart' | 'intervalStep'
type CronFieldChange =
  | { type: NumericFieldChange; value: number }
  | { type: 'list'; value: number[] }
  | { type: 'raw'; value: string }

interface CronFieldState {
  mode: CronFieldMode
  specific: number
  range: { start: number; end: number }
  interval: { start: number; step: number }
  list: number[]
  raw: string
}

function generateValue(state: CronFieldState, min: number): string {
  switch (state.mode) {
    case 'any': return '*'
    case 'specific': return String(state.specific)
    case 'range': return `${state.range.start}-${state.range.end}`
    case 'interval': return state.interval.start === min ? `*/${state.interval.step}` : `${state.interval.start}/${state.interval.step}`
    case 'list': return state.list.join(',')
    case 'raw': return state.raw
  }
}

const CronFieldInput: React.FC<CronFieldInputProps> = ({
  value,
  onChange,
  config,
  disabled = false,
}) => {
  const [state, setState] = useState<CronFieldState>({
    mode: 'any',
    specific: config.min,
    range: { start: config.min, end: config.max },
    interval: { start: config.min, step: 1 },
    list: [],
    raw: '',
  })
  const {
    mode, specific: specificValue, range: { start: rangeStart, end: rangeEnd },
    interval: { start: intervalStart, step: intervalStep }, list: listValues, raw: rawValue,
  } = state

  useEffect(() => {
    setState(previous => {
      if (value === '*') return { ...previous, mode: 'any' }
      if (value.includes('/')) {
        const [start, step] = value.split('/')
        return { ...previous, mode: 'interval', interval: { start: start === '*' ? config.min : parseInt(start), step: parseInt(step) } }
      }
      if (value.includes('-')) {
        const [start, end] = value.split('-')
        return { ...previous, mode: 'range', range: { start: parseInt(start), end: parseInt(end) } }
      }
      if (value.includes(',')) return { ...previous, mode: 'list', list: value.split(',').map(v => parseInt(v.trim())) }
      if (!isNaN(parseInt(value))) return { ...previous, mode: 'specific', specific: parseInt(value) }
      return { ...previous, mode: 'raw', raw: value }
    })
  }, [value, config.min, config.max])

  const acceptState = (next: CronFieldState) => {
    setState(next)
    onChange(generateValue(next, config.min))
  }

  const handleModeChange = (newMode: CronFieldMode | null) => {
    if (newMode) acceptState({ ...state, mode: newMode })
  }

  const handleValueChange = (change: CronFieldChange) => {
    switch (change.type) {
      case 'specific':
        acceptState({ ...state, mode: 'specific', specific: change.value })
        break
      case 'rangeStart':
        acceptState({ ...state, mode: 'range', range: { ...state.range, start: change.value } })
        break
      case 'rangeEnd':
        acceptState({ ...state, mode: 'range', range: { ...state.range, end: change.value } })
        break
      case 'intervalStart':
        acceptState({ ...state, mode: 'interval', interval: { ...state.interval, start: change.value } })
        break
      case 'intervalStep':
        acceptState({ ...state, mode: 'interval', interval: { ...state.interval, step: change.value } })
        break
      case 'list':
        acceptState({ ...state, mode: 'list', list: change.value })
        break
      case 'raw':
        acceptState({ ...state, mode: 'raw', raw: change.value })
        break
    }
  }

  const handleNumberInput = (type: NumericFieldChange, inputValue: string, min: number, max: number) => {
    const num = parseInt(inputValue)
    if (!isNaN(num) && num >= min && num <= max) handleValueChange({ type, value: num })
  }

  const toggleListValue = (val: number) => {
    const next = listValues.includes(val)
      ? listValues.filter(v => v !== val)
      : [...listValues, val].sort((a, b) => a - b)
    handleValueChange({ type: 'list', value: next })
  }

  const allValues = Array.from({ length: config.max - config.min + 1 }, (_, i) => config.min + i)

  const modeLabels: Record<CronFieldMode, string> = {
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
          itemToStringLabel={(v) => modeLabels[v] || String(v)}
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
              onValueChange={(val) => val && handleValueChange({ type: 'specific', value: parseInt(val) })}
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
            onValueChange={(val) => val && handleValueChange({ type: 'intervalStart', value: parseInt(val) })}
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
            onChange={(e) => handleValueChange({ type: 'raw', value: e.target.value })}
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
