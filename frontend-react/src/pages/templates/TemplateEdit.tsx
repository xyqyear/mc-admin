import React, { useEffect, useState, useMemo } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  Card,
  Button,
  Input,
  Form,
  Alert,
  Space,
  App,
  Tabs,
} from "antd";
import {
  SaveOutlined,
  ArrowLeftOutlined,
  FileTextOutlined,
} from "@ant-design/icons";
import { RJSFSchema, UiSchema } from "@rjsf/utils";
import validator from "@rjsf/validator-ajv8";
import ThemedForm from "@/components/forms/rjsfTheme";
import PageHeader from "@/components/layout/PageHeader";
import LoadingSpinner from "@/components/layout/LoadingSpinner";
import { ComposeYamlEditor } from "@/components/editors";
import { useTemplate } from "@/hooks/queries/base/useTemplateQueries";
import { useTemplateMutations } from "@/hooks/mutations/useTemplateMutations";
import type {
  VariableDefinition,
  TemplateCreateRequest,
  TemplateUpdateRequest,
} from "@/hooks/api/templateApi";

const { TextArea } = Input;

// System reserved variable names
const SYSTEM_VARIABLE_NAMES = [
  "name",
  "java_version",
  "game_version",
  "max_memory",
  "game_port",
  "rcon_port",
];

// Extract variables from YAML template
const extractVariablesFromYaml = (yaml: string): string[] => {
  const pattern = /\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g;
  const matches = yaml.matchAll(pattern);
  return [...new Set([...matches].map((m) => m[1]))];
};

// JSON Schema for variable definitions array
const variablesSchema: RJSFSchema = {
  type: "array",
  title: "自定义变量列表",
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
                type: "integer",
                title: "最大长度",
                minimum: 1,
              },
              pattern: {
                type: "string",
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
                type: "integer",
                title: "最小值",
              },
              max_value: {
                type: "integer",
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
                type: "number",
                title: "最小值",
              },
              max_value: {
                type: "number",
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
const variablesUiSchema: UiSchema = {
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
interface VariableFormData {
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

const TemplateEdit: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const copyFromId = searchParams.get("copyFrom");
  const { message } = App.useApp();

  const isEditMode = !!id;
  const templateId = id ? parseInt(id, 10) : copyFromId ? parseInt(copyFromId, 10) : null;

  // Form state
  const [form] = Form.useForm();
  const [yamlContent, setYamlContent] = useState("");
  const [variables, setVariables] = useState<VariableFormData[]>([]);
  const [activeTab, setActiveTab] = useState("yaml");

  // Load template data
  const { data: template, isLoading } = useTemplate(templateId);

  // Mutations
  const { useCreateTemplate, useUpdateTemplate } = useTemplateMutations();
  const createMutation = useCreateTemplate();
  const updateMutation = useUpdateTemplate();

  // Initialize form with template data
  useEffect(() => {
    if (template) {
      if (isEditMode) {
        form.setFieldsValue({
          name: template.name,
          description: template.description || "",
        });
      } else if (copyFromId) {
        // Copy mode - don't copy name
        form.setFieldsValue({
          name: "",
          description: template.description || "",
        });
      }
      setYamlContent(template.yaml_template);
      // Convert API variables to form data format
      setVariables(
        template.variables.map((v) => ({
          type: v.type,
          name: v.name,
          display_name: v.display_name,
          description: v.description,
          default: v.default,
          ...("min_value" in v ? { min_value: v.min_value } : {}),
          ...("max_value" in v ? { max_value: v.max_value } : {}),
          ...("max_length" in v ? { max_length: v.max_length } : {}),
          ...("pattern" in v ? { pattern: v.pattern } : {}),
          ...("options" in v ? { options: v.options } : {}),
        })) as VariableFormData[]
      );
    }
  }, [template, isEditMode, copyFromId, form]);

  // Extract variables from YAML
  const yamlVariables = useMemo(
    () => extractVariablesFromYaml(yamlContent),
    [yamlContent]
  );

  // Validation: check for undefined variables and missing system variables
  const validationErrors = useMemo(() => {
    const errors: string[] = [];
    const definedVars = new Set([
      ...SYSTEM_VARIABLE_NAMES,
      ...variables.map((v) => v.name).filter(Boolean),
    ]);

    // Check for undefined variables in YAML
    const undefinedVars = yamlVariables.filter((v) => !definedVars.has(v));
    if (undefinedVars.length > 0) {
      errors.push(`YAML 中使用了未定义的变量: ${undefinedVars.join(", ")}`);
    }

    // Check for missing system variables in YAML
    const missingSystemVars = SYSTEM_VARIABLE_NAMES.filter(
      (v) => !yamlVariables.includes(v)
    );
    if (missingSystemVars.length > 0) {
      errors.push(
        `YAML 模板缺少系统保留变量: ${missingSystemVars.join(", ")}`
      );
    }

    // Check for duplicate variable names
    const varNames = variables.map((v) => v.name).filter(Boolean);
    const duplicates = varNames.filter(
      (name, index) => varNames.indexOf(name) !== index
    );
    if (duplicates.length > 0) {
      errors.push(`变量名重复: ${[...new Set(duplicates)].join(", ")}`);
    }

    // Check for conflicts with system variables
    const conflicts = variables.filter((v) =>
      SYSTEM_VARIABLE_NAMES.includes(v.name)
    );
    if (conflicts.length > 0) {
      errors.push(
        `变量名与系统保留变量冲突: ${conflicts.map((v) => v.name).join(", ")}`
      );
    }

    return errors;
  }, [yamlVariables, variables]);

  // Handle variables form change
  const handleVariablesChange = (data: { formData?: VariableFormData[] }) => {
    setVariables(data.formData || []);
  };

  // Handle save
  const handleSave = async () => {
    try {
      const values = await form.validateFields();

      if (!yamlContent.trim()) {
        message.error("请输入 YAML 模板内容");
        return;
      }

      if (validationErrors.length > 0) {
        message.error("请先修复验证错误");
        return;
      }

      // Convert form variables to API format
      // Helper: conditionally include default field
      const includeDefault = (value: unknown) =>
        value !== undefined && value !== null ? { default: value } : {};

      const apiVariables = variables
        .filter((v) => v.name && v.display_name) // Filter out incomplete entries
        .map((v) => {
          const base = {
            name: v.name,
            display_name: v.display_name,
            description: v.description,
          };

          switch (v.type) {
            case "int":
              return {
                ...base,
                type: "int" as const,
                ...includeDefault(v.default),
                min_value: v.min_value,
                max_value: v.max_value,
              };
            case "float":
              return {
                ...base,
                type: "float" as const,
                ...includeDefault(v.default),
                min_value: v.min_value,
                max_value: v.max_value,
              };
            case "string":
              return {
                ...base,
                type: "string" as const,
                ...includeDefault(v.default),
                max_length: v.max_length,
                pattern: v.pattern,
              };
            case "enum":
              return {
                ...base,
                type: "enum" as const,
                ...includeDefault(v.default),
                options: v.options || [],
              };
            case "bool":
              return {
                ...base,
                type: "bool" as const,
                ...includeDefault(v.default),
              };
          }
        }) as VariableDefinition[];

      if (isEditMode && id) {
        const request: TemplateUpdateRequest = {
          name: values.name,
          description: values.description || undefined,
          yaml_template: yamlContent,
          variables: apiVariables,
        };
        await updateMutation.mutateAsync({ id: parseInt(id, 10), request });
        navigate("/templates");
      } else {
        const request: TemplateCreateRequest = {
          name: values.name,
          description: values.description || undefined,
          yaml_template: yamlContent,
          variables: apiVariables,
        };
        await createMutation.mutateAsync(request);
        navigate("/templates");
      }
    } catch (error) {
      console.error("Save failed:", error);
    }
  };

  if (isLoading && templateId) {
    return <LoadingSpinner />;
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={isEditMode ? "编辑模板" : copyFromId ? "复制模板" : "新建模板"}
        icon={<FileTextOutlined />}
      />

      <Form form={form} layout="vertical">
        <Card title="基本信息" className="mb-4">
          <Form.Item
            name="name"
            label="模板名称"
            rules={[
              { required: true, message: "请输入模板名称" },
              { max: 100, message: "模板名称最长 100 个字符" },
            ]}
          >
            <Input placeholder="例如: paper-server" />
          </Form.Item>

          <Form.Item name="description" label="描述">
            <TextArea
              placeholder="模板描述（可选）"
              rows={2}
              maxLength={500}
            />
          </Form.Item>
        </Card>

        <Card className="mb-4">
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: "yaml",
                label: "YAML 模板",
                children: (
                  <div className="space-y-4">
                    <Alert
                      type="info"
                      showIcon
                      message="使用 {变量名} 格式定义占位符"
                      description={
                        <div>
                          <p>系统保留变量: {SYSTEM_VARIABLE_NAMES.join(", ")}</p>
                          <p>
                            当前 YAML 中使用的变量:{" "}
                            {yamlVariables.length > 0
                              ? yamlVariables.join(", ")
                              : "无"}
                          </p>
                        </div>
                      }
                    />

                    <ComposeYamlEditor
                      value={yamlContent}
                      onChange={(value) => setYamlContent(value || "")}
                      autoHeight
                      minHeight={400}
                      theme="vs-light"
                      path="template.yml"
                    />
                  </div>
                ),
              },
              {
                key: "variables",
                label: `自定义变量 (${variables.length})`,
                children: (
                  <div className="space-y-4">
                    <Alert
                      type="info"
                      showIcon
                      message="定义用户自定义变量"
                      description="系统保留变量（name, java_version 等）无需定义，会自动包含在表单中。使用下方表单添加自定义变量。"
                    />

                    <ThemedForm
                      schema={variablesSchema}
                      uiSchema={variablesUiSchema}
                      formData={variables}
                      validator={validator}
                      onChange={handleVariablesChange}
                      liveValidate
                      tagName="div"
                      showErrorList={false}
                    >
                      {/* Hide submit button */}
                      <div />
                    </ThemedForm>
                  </div>
                ),
              },
            ]}
          />
        </Card>

        {validationErrors.length > 0 && (
          <Alert
            type="error"
            showIcon
            message="验证错误"
            description={
              <ul className="list-disc pl-4">
                {validationErrors.map((error, index) => (
                  <li key={index}>{error}</li>
                ))}
              </ul>
            }
            className="mb-4"
          />
        )}

        <Card>
          <div className="flex justify-between">
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
              返回
            </Button>
            <Space>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSave}
                loading={createMutation.isPending || updateMutation.isPending}
                disabled={validationErrors.length > 0}
              >
                {isEditMode ? "保存" : "创建"}
              </Button>
            </Space>
          </div>
        </Card>
      </Form>
    </div>
  );
};

export default TemplateEdit;
