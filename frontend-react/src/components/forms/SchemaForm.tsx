import { withTheme } from '@rjsf/core'
import { Theme as ShadcnTheme } from '@rjsf/shadcn'
import validator from '@rjsf/validator-ajv8'
import { RJSFSchema } from '@rjsf/utils'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'

const Form = withTheme(ShadcnTheme)

interface SchemaFormProps {
  schema: RJSFSchema
  formData: any
  onChange: (data: any) => void
  onSubmit?: (data: any) => void
  loading?: boolean
  disabled?: boolean
  showSubmitButton?: boolean
  submitButtonText?: string
  formKey?: number | string
  liveValidate?: 'onChange' | 'onBlur'
  showErrorList?: false | 'top' | 'bottom' | undefined
}

const SchemaForm = ({
  schema,
  formData,
  onChange,
  onSubmit,
  loading = false,
  disabled = false,
  showSubmitButton = false,
  submitButtonText = '提交',
  formKey,
  liveValidate = 'onChange',
  showErrorList = false,
}: SchemaFormProps) => {
  const handleFormChange = ({ formData: newFormData }: any) => {
    onChange(newFormData)
  }

  const handleFormSubmit = ({ formData: submitData }: any) => {
    if (onSubmit) {
      onSubmit(submitData)
    }
  }

  const handleFormError = (errors: any) => {
    console.log('Form validation errors:', errors)
  }

  return (
    <Form
      key={formKey}
      schema={schema}
      formData={formData}
      validator={validator}
      onChange={handleFormChange}
      onSubmit={handleFormSubmit}
      onError={handleFormError}
      showErrorList={showErrorList}
      liveValidate={liveValidate}
      disabled={disabled}
    >
      {showSubmitButton ? (
        <Button type="submit" disabled={loading || disabled}>
          {loading && <Spinner className="size-4" />}
          {submitButtonText}
        </Button>
      ) : (
        <div />
      )}
    </Form>
  )
}

export default SchemaForm