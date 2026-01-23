import React from 'react'
import { Button } from 'antd'
import Form from '@rjsf/antd'
import validator from '@rjsf/validator-ajv8'
import { RJSFSchema } from '@rjsf/utils'

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

const SchemaForm: React.FC<SchemaFormProps> = ({
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
  showErrorList = false
}) => {
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
    <div className="schema-form-container">
      <style>
        {`
            .schema-form-container #root {
              height: auto !important;
            }
          `}
      </style>
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
        {showSubmitButton && (
          <Button
            type="primary"
            htmlType="submit"
            loading={loading}
            disabled={disabled}
          >
            {submitButtonText}
          </Button>
        )}
        {!showSubmitButton && <div />}
      </Form>
    </div>
  )
}

export default SchemaForm