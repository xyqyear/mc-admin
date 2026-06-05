import React, { useRef, useCallback } from "react"
import type { IChangeEvent } from "@rjsf/core"
import type Form from "@rjsf/core"
import type { CustomValidator } from "@rjsf/utils"
import validator from "@rjsf/validator-ajv8"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"

import ThemedForm from "@/components/forms/rjsfTheme"
import {
  singleVariableSchema,
  singleVariableUiSchema,
  type VariableFormData,
} from "./variableSchemas"

interface VariableEditDialogProps {
  open: boolean
  mode: "add" | "edit"
  initialData?: Partial<VariableFormData>
  onOk: (data: VariableFormData) => void
  onCancel: () => void
}

const DEFAULT_INITIAL: Partial<VariableFormData> = {
  type: "string",
  name: "",
  display_name: "",
}

const customValidate: CustomValidator<VariableFormData> = (formData, errors) => {
  if (
    formData?.type === "enum" &&
    formData.default != null &&
    formData.default !== ""
  ) {
    if (formData.options && !formData.options.includes(formData.default as string)) {
      errors.default!.addError("默认值必须是选项列表中的一个")
    }
  }
  return errors
}

const VariableEditDialog: React.FC<VariableEditDialogProps> = ({
  open,
  mode,
  initialData,
  onOk,
  onCancel,
}) => {
  const formRef = useRef<Form>(null)

  const handleOk = useCallback(() => {
    formRef.current?.submit()
  }, [])

  const handleSubmit = useCallback(
    (e: IChangeEvent<VariableFormData>) => {
      if (e.formData) {
        onOk(e.formData)
      }
    },
    [onOk]
  )

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="grid-rows-[auto_minmax(0,1fr)_auto] max-h-[85vh] sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{mode === "add" ? "添加变量" : "编辑变量"}</DialogTitle>
        </DialogHeader>
        <div className="-mx-4 min-h-0 overflow-y-auto px-4">
          {open && (
            <ThemedForm
              ref={formRef}
              schema={singleVariableSchema}
              uiSchema={singleVariableUiSchema}
              formData={initialData ?? DEFAULT_INITIAL}
              validator={validator}
              onSubmit={handleSubmit}
              customValidate={customValidate}
              liveValidate
              showErrorList={false}
            >
              <div />
            </ThemedForm>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>取消</Button>
          <Button onClick={handleOk}>确定</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default VariableEditDialog
