import type { RJSFSchema, UiSchema } from "@rjsf/utils";

// Single variable JSON Schema (extracted from the former array schema's `items`)
export const singleVariableSchema: RJSFSchema = {
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
      maxLength: 50,
    },
    display_name: {
      type: "string",
      title: "显示名称",
      description: "在表单中显示的名称",
      minLength: 1,
      maxLength: 100,
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
};

export const singleVariableUiSchema: UiSchema = {
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
