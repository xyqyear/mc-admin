import { useState, type FormEvent } from 'react'
import { BooleanField, FormField, NumberField, StringListField, TextAreaField, TextField } from '@/shared/components/FormFields'
import { Alert, AlertDescription } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/shared/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/ui/select'
import { templateValueError } from '@/features/templates/variableValues'
import { convertToApiFormat } from '@/features/templates/ui/variableUtils'
import type { VariableFormData } from '@/features/templates/ui/variableFormData'

interface Props {
  open: boolean
  mode: 'add' | 'edit'
  initialData?: Partial<VariableFormData>
  onOk: (value: VariableFormData) => void
  onCancel: () => void
}

const typeLabels = { string: '字符串', int: '整数', float: '浮点数', enum: '枚举', bool: '布尔值' }

function VariableEditor({ initialData, onOk, onCancel }: Pick<Props, 'initialData' | 'onOk' | 'onCancel'>) {
  const [value, setValue] = useState<VariableFormData>({ type: 'string', name: '', display_name: '', ...initialData })
  const [error, setError] = useState<string>()
  const patch = (fields: Partial<VariableFormData>) => { setValue({ ...value, ...fields }); setError(undefined) }
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(value.name)) { setError('变量名必须以字母或下划线开头，只能包含字母、数字和下划线'); return }
    if (value.min_value != null && value.max_value != null && value.min_value > value.max_value) { setError('最小值不能大于最大值'); return }
    if (value.type === 'string' && value.pattern) {
      try { new RegExp(value.pattern) } catch { setError('正则表达式无效'); return }
    }
    if (value.type === 'enum' && (!value.options?.length || value.options.some(option => option === '') || new Set(value.options).size !== value.options.length)) { setError('枚举选项不能为空或重复'); return }
    const definition = convertToApiFormat([value])[0]
    if (value.default != null) {
      const validationError = templateValueError(definition, value.default)
      if (validationError) { setError(`默认值无效：${validationError}`); return }
    }
    onOk(value)
  }
  return <form className="contents" onSubmit={submit}>
    <div className="-mx-4 min-h-0 overflow-y-auto px-4 space-y-4">
      <FormField label="类型">{id => <Select value={value.type} onValueChange={type => {
        if (!type) return
        setValue({ type, name: value.name, display_name: value.display_name, description: value.description })
        setError(undefined)
      }} itemToStringLabel={type => typeLabels[type]}>
        <SelectTrigger id={id}><SelectValue /></SelectTrigger>
        <SelectContent>{Object.entries(typeLabels).map(([type, label]) => <SelectItem key={type} value={type}>{label}</SelectItem>)}</SelectContent>
      </Select>}</FormField>
      <TextField label="变量名" value={value.name} onChange={name => patch({ name })} required maxLength={50} description="在 YAML 模板中使用 {变量名} 引用" />
      <TextField label="显示名称" value={value.display_name} onChange={display_name => patch({ display_name })} required maxLength={100} />
      <TextAreaField label="描述" value={value.description ?? ''} onChange={description => patch({ description })} rows={2} />
      {(value.type === 'int' || value.type === 'float') && <>
        <NumberField label="最小值" value={value.min_value} onChange={min_value => patch({ min_value })} step={value.type === 'int' ? 1 : 'any'} />
        <NumberField label="最大值" value={value.max_value} onChange={max_value => patch({ max_value })} step={value.type === 'int' ? 1 : 'any'} />
      </>}
      {value.type === 'string' && <>
        <NumberField label="最大长度" value={value.max_length} onChange={max_length => patch({ max_length })} min={1} step={1} />
        <TextField label="正则模式" value={value.pattern ?? ''} onChange={pattern => patch({ pattern: pattern || undefined })} placeholder="例如: ^[a-z0-9-]+$" />
      </>}
      {value.type === 'enum' && <StringListField label="选项" value={value.options ?? []} onChange={options => patch({ options })} orderable />}
      <BooleanField label="设置默认值" value={value.default !== undefined} onChange={enabled => patch({ default: enabled ? value.type === 'bool' ? false : value.type === 'int' || value.type === 'float' ? 0 : '' : undefined })} />
      {value.default !== undefined && (value.type === 'bool'
        ? <BooleanField label="默认值" value={value.default === true} onChange={next => patch({ default: next })} />
        : value.type === 'int' || value.type === 'float'
          ? <NumberField label="默认值" value={Number(value.default)} required step={value.type === 'int' ? 1 : 'any'} onChange={next => patch({ default: next ?? Number.NaN })} />
          : <TextField label="默认值" value={String(value.default)} onChange={next => patch({ default: next })} />)}
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
    </div>
    <DialogFooter><Button type="button" variant="outline" onClick={onCancel}>取消</Button><Button type="submit">确定</Button></DialogFooter>
  </form>
}

export default function VariableEditDialog({ open, mode, initialData, onOk, onCancel }: Props) {
  return <Dialog open={open} onOpenChange={next => { if (!next) onCancel() }}>
    <DialogContent className="grid-rows-[auto_minmax(0,1fr)_auto] max-h-[85vh] sm:max-w-lg">
      <DialogHeader><DialogTitle>{mode === 'add' ? '添加变量' : '编辑变量'}</DialogTitle></DialogHeader>
      {open && <VariableEditor initialData={initialData} onOk={onOk} onCancel={onCancel} />}
    </DialogContent>
  </Dialog>
}
