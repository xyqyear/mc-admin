import { useId, useState, type ComponentProps, type ReactNode } from 'react'
import { Plus, Trash2, ArrowUp, ArrowDown } from 'lucide-react'
import { Button } from '@/shared/ui/button'
import { Checkbox } from '@/shared/ui/checkbox'
import { Input } from '@/shared/ui/input'
import { Textarea } from '@/shared/ui/textarea'
import { Field, FieldContent, FieldDescription, FieldError, FieldLabel } from '@/shared/ui/field'

interface FieldProps {
  label: string
  description?: string
  error?: string
}

export function FormField({ label, description, error, children }: FieldProps & { children: (id: string) => ReactNode }) {
  const id = useId()
  return <Field data-invalid={Boolean(error)}>
    <FieldLabel htmlFor={id}>{label}</FieldLabel>
    {children(id)}
    {description && <FieldDescription>{description}</FieldDescription>}
    {error && <FieldError>{error}</FieldError>}
  </Field>
}

export function TextField({ label, description, error, value, onChange, ...props }: FieldProps & Omit<ComponentProps<typeof Input>, 'value' | 'onChange'> & { value: string; onChange: (value: string) => void }) {
  return <FormField label={label} description={description} error={error}>{id => <Input {...props} id={id} value={value} onChange={event => onChange(event.target.value)} aria-invalid={Boolean(error)} />}</FormField>
}

export function TextAreaField({ label, description, error, value, onChange, ...props }: FieldProps & Omit<ComponentProps<typeof Textarea>, 'value' | 'onChange'> & { value: string; onChange: (value: string) => void }) {
  return <FormField label={label} description={description} error={error}>{id => <Textarea {...props} id={id} value={value} onChange={event => onChange(event.target.value)} aria-invalid={Boolean(error)} />}</FormField>
}

export function NumberField({ value, onChange, ...props }: FieldProps & Omit<ComponentProps<typeof Input>, 'value' | 'onChange' | 'type'> & { value: number | null | undefined; onChange: (value: number | undefined) => void }) {
  return <TextField {...props} type="number" value={value == null || Number.isNaN(value) ? '' : String(value)} onChange={text => onChange(text === '' ? undefined : Number(text))} />
}

export function BooleanField({ label, description, error, value, onChange, disabled }: FieldProps & { value: boolean; onChange: (value: boolean) => void; disabled?: boolean }) {
  const id = useId()
  return <Field orientation="horizontal" data-invalid={Boolean(error)}>
    <Checkbox id={id} checked={value} onCheckedChange={checked => onChange(checked === true)} disabled={disabled} aria-invalid={Boolean(error)} />
    <FieldContent>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      {description && <FieldDescription>{description}</FieldDescription>}
      {error && <FieldError>{error}</FieldError>}
    </FieldContent>
  </Field>
}

export function StringListField({ label, description, value, onChange, multiline = false, orderable = false }: FieldProps & { value: string[]; onChange: (value: string[]) => void; multiline?: boolean; orderable?: boolean }) {
  return <fieldset className="space-y-3">
    <legend className="text-sm font-medium">{label}</legend>
    {description && <p className="text-sm text-muted-foreground">{description}</p>}
    {value.map((item, index) => <div key={index} className="flex items-start gap-2">
      {multiline
        ? <Textarea aria-label={`${label} ${index + 1}`} value={item} rows={3} onChange={event => onChange(value.map((entry, i) => i === index ? event.target.value : entry))} />
        : <Input aria-label={`${label} ${index + 1}`} value={item} onChange={event => onChange(value.map((entry, i) => i === index ? event.target.value : entry))} />}
      {orderable && <>
        <Button type="button" variant="outline" size="icon" aria-label={`上移${label} ${index + 1}`} disabled={index === 0} onClick={() => { const next = [...value]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; onChange(next) }}><ArrowUp /></Button>
        <Button type="button" variant="outline" size="icon" aria-label={`下移${label} ${index + 1}`} disabled={index === value.length - 1} onClick={() => { const next = [...value]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; onChange(next) }}><ArrowDown /></Button>
      </>}
      <Button type="button" variant="outline" size="icon" aria-label={`删除${label} ${index + 1}`} onClick={() => onChange(value.filter((_, i) => i !== index))}><Trash2 /></Button>
    </div>)}
    <Button type="button" variant="outline" size="sm" onClick={() => onChange([...value, ''])}><Plus />添加{label}</Button>
  </fieldset>
}

export function StringMapField({ label, value, onChange }: { label: string; value: Record<string, string>; onChange: (value: Record<string, string>) => void }) {
  const [state, setState] = useState<{ value: Record<string, string>; rows: string[][] }>({ value, rows: Object.entries(value) })
  if (state.value !== value) setState({ value, rows: Object.entries(value) })
  const update = (rows: string[][]) => {
    const valid = rows.every(([key]) => key !== '') && new Set(rows.map(([key]) => key)).size === rows.length
    const next = valid ? Object.fromEntries(rows) as Record<string, string> : state.value
    setState({ value: next, rows })
    if (valid) onChange(next)
  }
  return <fieldset className="space-y-3">
    <legend className="text-sm font-medium">{label}</legend>
    {state.rows.map(([key, text], index) => <div className="flex items-start gap-2" key={index}>
      <Input aria-label={`${label}键 ${index + 1}`} required value={key} ref={node => { node?.setCustomValidity(state.rows.some(([other], i) => i !== index && other === key) ? '键不能重复' : '') }} onChange={event => update(state.rows.map((row, i) => i === index ? [event.target.value, text] : row))} />
      <Input aria-label={`${label}值 ${index + 1}`} value={text} onChange={event => update(state.rows.map((row, i) => i === index ? [key, event.target.value] : row))} />
      <Button type="button" variant="outline" size="icon" aria-label={`删除${label} ${index + 1}`} onClick={() => update(state.rows.filter((_, i) => i !== index))}><Trash2 /></Button>
    </div>)}
    <Button type="button" variant="outline" size="sm" onClick={() => update([...state.rows, ['', '']])}><Plus />添加{label}</Button>
  </fieldset>
}
