export interface VariableFormData {
  type: 'int' | 'float' | 'string' | 'enum' | 'bool'
  name: string
  display_name: string
  description?: string
  default?: string | number | boolean
  min_value?: number
  max_value?: number
  max_length?: number
  pattern?: string
  options?: string[]
}
