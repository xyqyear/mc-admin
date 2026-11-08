import type { VariableDefinition } from '@/features/templates/contracts'

export function templateDefaultValues(definitions: VariableDefinition[]): Record<string, unknown> {
  return Object.fromEntries(definitions.flatMap(variable => variable.default != null
    ? [[variable.name, variable.default]]
    : variable.type === 'bool' ? [[variable.name, false]] : []))
}

export function templateValueError(variable: VariableDefinition, value: unknown): string | undefined {
  if (value == null) return '请填写此参数'
  switch (variable.type) {
    case 'int':
    case 'float':
      if (typeof value !== 'number' || !Number.isFinite(value)) return '请输入有效数字'
      if (variable.type === 'int' && !Number.isInteger(value)) return '请输入整数'
      if (variable.min_value != null && value < variable.min_value) return `不能小于 ${variable.min_value}`
      if (variable.max_value != null && value > variable.max_value) return `不能大于 ${variable.max_value}`
      break
    case 'string':
      if (typeof value !== 'string') return '请输入字符串'
      if (variable.max_length != null && value.length > variable.max_length) return `最多 ${variable.max_length} 个字符`
      if (variable.pattern) {
        try { if (!new RegExp(variable.pattern).test(value)) return '输入不符合格式要求' }
        catch { return '变量的正则表达式无效' }
      }
      break
    case 'enum':
      if (typeof value !== 'string' || !variable.options.includes(value)) return '请选择一个有效选项'
      break
    case 'bool':
      if (typeof value !== 'boolean') return '请选择布尔值'
      break
  }
}

export function templateValuesValid(definitions: VariableDefinition[], values: Record<string, unknown>): boolean {
  return definitions.every(variable => !templateValueError(variable, values[variable.name]))
}
