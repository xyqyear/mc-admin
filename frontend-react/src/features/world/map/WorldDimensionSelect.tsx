import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/ui/select'

interface WorldDimensionSelectProps {
  options: { value: string; label: string }[]
  value: string | null
  onChange: (value: string) => void
}

export function WorldDimensionSelect({ options, value, onChange }: WorldDimensionSelectProps) {
  return (
    <Select
      items={options}
      value={value}
      onValueChange={(next) => { if (typeof next === 'string') onChange(next) }}
      itemToStringLabel={(next) => options.find(option => option.value === next)?.label ?? String(next)}
    >
      <SelectTrigger className="w-65">
        <SelectValue placeholder="选择维度" />
      </SelectTrigger>
      <SelectContent>
        {options.map(option => (
          <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
