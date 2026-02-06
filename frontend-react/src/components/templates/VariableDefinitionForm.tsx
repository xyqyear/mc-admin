import React from "react";
import { RJSFSchema, UiSchema } from "@rjsf/utils";
import validator from "@rjsf/validator-ajv8";
import ThemedForm from "@/components/forms/rjsfTheme";

// JSON Schema for variable definitions array
export const variablesSchema: RJSFSchema = {
  type: "array",
  title: "变量列表",
  items: {
    type: "object",
    required: ["type", "name", "display_name"],
    properties: {
      type: {
        type: "string",
        title: "类型",
        oneOf: [
          { const: "string", title: "字符串" },
          { const: "int", title: "整数" },
          { const: "float", title: "浮点数" },
          { const: "enum", title: "枚举" },
          { const: "bool", title: "布尔值" },
        ],
        default: "string",
      },
      name: {
        type: "string",
        title: "变量名",
        description: "在 YAML 模板中使用 {变量名} 引用",
        pattern: "^[a-zA-Z_][a-zA-Z0-9_]*$",
      },
      display_name: {
        type: "string",
        title: "显示名称",
        description: "在表单中显示的名称",
      },
      description: {
        type: ["string", "null"],
        title: "描述",
        description: "变量的详细说明（可选）",
      },
    },
    dependencies: {
      type: {
        oneOf: [
          {
            properties: {
              type: { enum: ["string"] },
              default: {
                type: ["string", "null"],
                title: "默认值",
              },
              max_length: {
                type: ["integer", "null"],
                title: "最大长度",
                minimum: 1,
              },
              pattern: {
                type: ["string", "null"],
                title: "正则模式",
                description: "用于验证输入的正则表达式",
              },
            },
          },
          {
            properties: {
              type: { enum: ["int"] },
              default: {
                type: ["integer", "null"],
                title: "默认值",
              },
              min_value: {
                type: ["integer", "null"],
                title: "最小值",
              },
              max_value: {
                type: ["integer", "null"],
                title: "最大值",
              },
            },
          },
          {
            properties: {
              type: { enum: ["float"] },
              default: {
                type: ["number", "null"],
                title: "默认值",
              },
              min_value: {
                type: ["number", "null"],
                title: "最小值",
              },
              max_value: {
                type: ["number", "null"],
                title: "最大值",
              },
            },
          },
          {
            properties: {
              type: { enum: ["enum"] },
              default: {
                type: ["string", "null"],
                title: "默认值",
                description: "必须是选项之一（可选）",
              },
              options: {
                type: "array",
                title: "选项列表",
                items: {
                  type: "string",
                },
                minItems: 1,
                uniqueItems: true,
              },
            },
            required: ["options"],
          },
          {
            properties: {
              type: { enum: ["bool"] },
              default: {
                type: ["boolean", "null"],
                title: "默认值",
              },
            },
          },
        ],
      },
    },
  },
};

// UI Schema for better form layout
export const variablesUiSchema: UiSchema = {
  "ui:options": {
    orderable: true,
    addable: true,
    removable: true,
  },
  items: {
    "ui:order": ["type", "name", "display_name", "description", "default", "*"],
    description: {
      "ui:widget": "textarea",
      "ui:options": {
        rows: 2,
      },
    },
    pattern: {
      "ui:placeholder": "例如: ^[a-z0-9-]+$",
    },
    options: {
      "ui:options": {
        orderable: true,
      },
    },
  },
};

// Internal form data type (matches rjsf output)
export interface VariableFormData {
  type: "int" | "float" | "string" | "enum" | "bool";
  name: string;
  display_name: string;
  description?: string;
  default?: string | number | boolean;
  min_value?: number;
  max_value?: number;
  max_length?: number;
  pattern?: string;
  options?: string[];
}

interface VariableDefinitionFormProps {
  value: VariableFormData[];
  onChange: (variables: VariableFormData[]) => void;
  disabled?: boolean;
  title?: string;
}

const VariableDefinitionForm: React.FC<VariableDefinitionFormProps> = ({
  value,
  onChange,
  disabled = false,
  title,
}) => {
  const handleChange = (data: { formData?: VariableFormData[] }) => {
    onChange(data.formData || []);
  };

  const schema = title
    ? { ...variablesSchema, title }
    : variablesSchema;

  return (
    <ThemedForm
      schema={schema}
      uiSchema={variablesUiSchema}
      formData={value}
      validator={validator}
      onChange={handleChange}
      liveValidate
      tagName="div"
      showErrorList={false}
      disabled={disabled}
    >
      {/* Hide submit button */}
      <div />
    </ThemedForm>
  );
};

export default VariableDefinitionForm;
