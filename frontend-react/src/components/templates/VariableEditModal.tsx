import React, { useRef, useCallback } from "react";
import { Modal } from "antd";
import type { IChangeEvent } from "@rjsf/core";
import type Form from "@rjsf/core";
import type { CustomValidator } from "@rjsf/utils";
import validator from "@rjsf/validator-ajv8";
import ThemedForm from "@/components/forms/rjsfTheme";
import {
  singleVariableSchema,
  singleVariableUiSchema,
  type VariableFormData,
} from "./variableSchemas";

interface VariableEditModalProps {
  open: boolean;
  mode: "add" | "edit";
  initialData?: Partial<VariableFormData>;
  onOk: (data: VariableFormData) => void;
  onCancel: () => void;
}

const DEFAULT_INITIAL: Partial<VariableFormData> = {
  type: "string",
  name: "",
  display_name: "",
};

const customValidate: CustomValidator<VariableFormData> = (formData, errors) => {
  if (
    formData?.type === "enum" &&
    formData.default != null &&
    formData.default !== ""
  ) {
    if (formData.options && !formData.options.includes(formData.default as string)) {
      errors.default!.addError("默认值必须是选项列表中的一个");
    }
  }
  return errors;
};

const VariableEditModal: React.FC<VariableEditModalProps> = ({
  open,
  mode,
  initialData,
  onOk,
  onCancel,
}) => {
  const formRef = useRef<Form>(null);

  const handleOk = useCallback(() => {
    formRef.current?.submit();
  }, []);

  const handleSubmit = useCallback(
    (e: IChangeEvent<VariableFormData>) => {
      if (e.formData) {
        onOk(e.formData);
      }
    },
    [onOk]
  );

  return (
    <Modal
      title={mode === "add" ? "添加变量" : "编辑变量"}
      open={open}
      onOk={handleOk}
      onCancel={onCancel}
      destroyOnHidden
      width={520}
      okText="确定"
      cancelText="取消"
    >
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
        {/* Hide default submit button */}
        <div />
      </ThemedForm>
    </Modal>
  );
};

export default VariableEditModal;
