import validator from '@rjsf/validator-ajv8'
import type { IChangeEvent } from '@rjsf/core'
import type { RJSFSchema } from '@rjsf/utils'
import Form from '@/shared/forms/rjsfTheme'

interface SchemaFormProps {
  schema: RJSFSchema
  formData: Record<string, unknown>
  onChange: (data: Record<string, unknown> | undefined) => void
}

const SchemaForm = ({ schema, formData, onChange }: SchemaFormProps) => (
  <Form
    schema={schema}
    formData={formData}
    validator={validator}
    onChange={({ formData: data }: IChangeEvent<Record<string, unknown>>) => onChange(data)}
    onSubmit={() => undefined}
    showErrorList={false}
    liveValidate="onChange"
  >
    <div />
  </Form>
)

export default SchemaForm
