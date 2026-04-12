import React from 'react'
import { RotateCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'

interface CronJobFiltersProps {
  identifierOptions: { label: string; value: string }[]
  filters: {
    identifier?: string
    status: string[]
  }
  onChange: (filters: { identifier?: string; status: string[] }) => void
  onReset: () => void
  loading?: boolean
}

const statusOptions = [
  { label: '运行中', value: 'active' },
  { label: '已暂停', value: 'paused' },
  { label: '已取消', value: 'cancelled' },
]

const CronJobFilters: React.FC<CronJobFiltersProps> = ({
  identifierOptions,
  filters,
  onChange,
  onReset,
  loading = false,
}) => {
  const handleIdentifierChange = (value: string | null) => {
    onChange({
      ...filters,
      identifier: !value || value === '__all__' ? undefined : value,
    })
  }

  const toggleStatus = (value: string) => {
    const current = filters.status
    const next = current.includes(value)
      ? current.filter(s => s !== value)
      : [...current, value]
    onChange({ ...filters, status: next })
  }

  return (
    <div className="flex flex-wrap items-center gap-3 pl-2 mb-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-muted-foreground">任务类型</span>
        <Select
          value={filters.identifier || '__all__'}
          onValueChange={handleIdentifierChange}
          itemToStringLabel={(v) => {
            if (v === '__all__') return '全部类型'
            return identifierOptions.find(o => o.value === v)?.label || String(v)
          }}
        >
          <SelectTrigger className="w-44">
            <SelectValue placeholder="选择任务类型" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">全部类型</SelectItem>
            {identifierOptions.map(opt => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-muted-foreground">任务状态</span>
        <div className="flex gap-1">
          {statusOptions.map(opt => {
            const isActive = filters.status.includes(opt.value)
            return (
              <Badge
                key={opt.value}
                variant={isActive ? 'default' : 'outline'}
                className="cursor-pointer select-none"
                onClick={() => toggleStatus(opt.value)}
              >
                {opt.label}
              </Badge>
            )
          })}
        </div>
      </div>

      <Button
        variant="outline"
        size="sm"
        onClick={onReset}
        disabled={loading}
      >
        <RotateCw className="mr-1 h-3.5 w-3.5" />
        重置
      </Button>
    </div>
  )
}

export default CronJobFilters
