import type { VariableDefinition } from '@/features/templates/contracts'
import { templateValueError } from '@/features/templates/variableValues'
import { BooleanField, FormField, NumberField, TextField } from '@/shared/components/FormFields'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/ui/select'

interface Props {
  definitions: VariableDefinition[]
  value: Record<string, unknown>
  onChange: (value: Record<string, unknown>) => void
  readOnlyName?: boolean
}

export default function TemplateVariablesForm({ definitions, value, onChange, readOnlyName = false }: Props) {
  return <div className="space-y-5">{definitions.map(variable => {
    const current = value[variable.name]
    const error = templateValueError(variable, current)
    const update = (next: unknown) => onChange({ ...value, [variable.name]: next })
    const common = { label: variable.display_name, description: variable.description ?? undefined, error }
    switch (variable.type) {
      case 'int':
      case 'float':
        return <NumberField key={variable.name} {...common} value={typeof current === 'number' ? current : undefined} onChange={update} min={variable.min_value ?? undefined} max={variable.max_value ?? undefined} step={variable.type === 'int' ? 1 : 'any'} required />
      case 'bool':
        return <BooleanField key={variable.name} {...common} value={current === true} onChange={update} />
      case 'enum':
        return <FormField key={variable.name} {...common}>{id => <Select value={typeof current === 'string' ? current : null} onValueChange={next => update(next ?? undefined)}>
          <SelectTrigger id={id}><SelectValue placeholder="请选择" /></SelectTrigger>
          <SelectContent>{variable.options.map(option => <SelectItem key={option} value={option}>{option}</SelectItem>)}</SelectContent>
        </Select>}</FormField>
      case 'string':
        return <TextField key={variable.name} {...common} description={readOnlyName && variable.name === 'name' ? '服务器名称不可修改' : common.description} value={typeof current === 'string' ? current : ''} onChange={update} maxLength={variable.max_length ?? undefined} readOnly={readOnlyName && variable.name === 'name'} />
    }
  })}</div>
}
