import React, { useEffect, useState, useMemo, useRef } from "react";
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
  Modal,
} from "antd";
import {
  SaveOutlined,
  ArrowLeftOutlined,
  FileTextOutlined,
  DiffOutlined,
  ExclamationCircleOutlined,
} from "@ant-design/icons";
import PageHeader from "@/components/layout/PageHeader";
import LoadingSpinner from "@/components/layout/LoadingSpinner";
import { ComposeYamlEditor, MonacoDiffEditor } from "@/components/editors";
import {
  VariableDefinitionForm,
  convertToFormData,
  convertToApiFormat,
  type VariableFormData,
} from "@/components/templates";
import {
  useTemplate,
  useDefaultVariables,
} from "@/hooks/queries/base/useTemplateQueries";
import { useTemplateMutations } from "@/hooks/mutations/useTemplateMutations";
import type {
  VariableDefinition,
  TemplateCreateRequest,
  TemplateUpdateRequest,
} from "@/hooks/api/templateApi";

const { TextArea } = Input;

// Extract variables from YAML template
const extractVariablesFromYaml = (yaml: string): string[] => {
  const pattern = /\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g;
  const matches = yaml.matchAll(pattern);
  return [...new Set([...matches].map((m) => m[1]))];
};

const TemplateEdit: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const copyFromId = searchParams.get("copyFrom");
  const { message } = App.useApp();

  const isEditMode = !!id;
  const templateId = id ? parseInt(id, 10) : copyFromId ? parseInt(copyFromId, 10) : null;
  const isNewTemplate = !isEditMode && !copyFromId;

  // Form state
  const [form] = Form.useForm();
  const [yamlContent, setYamlContent] = useState("");
  const [variables, setVariables] = useState<VariableFormData[]>([]);

  const [defaultsLoaded, setDefaultsLoaded] = useState(false);
  const [isCompareVisible, setIsCompareVisible] = useState(false);
  const [diffTab, setDiffTab] = useState("yaml");

  // Store original values for comparison (only in edit mode)
  const originalYamlRef = useRef<string>("");
  const originalVariablesRef = useRef<VariableDefinition[]>([]);

  // Load template data
  const { data: template, isLoading, refetch: refetchTemplate } = useTemplate(templateId);

  // Load default variables for new templates
  const { data: defaultVariablesData, isLoading: isLoadingDefaults } =
    useDefaultVariables();

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
        // Store original values for comparison
        originalYamlRef.current = template.yaml_template;
        originalVariablesRef.current = template.variable_definitions;
      } else if (copyFromId) {
        // Copy mode - don't copy name
        form.setFieldsValue({
          name: "",
          description: template.description || "",
        });
      }
      setYamlContent(template.yaml_template);
      // Convert API variables to form data format
      setVariables(convertToFormData(template.variable_definitions));
      setDefaultsLoaded(true);
    }
  }, [template, isEditMode, copyFromId, form]);

  // Pre-fill default variables for new templates (not copy mode)
  useEffect(() => {
    if (isNewTemplate && defaultVariablesData?.variable_definitions && !defaultsLoaded) {
      setVariables(convertToFormData(defaultVariablesData.variable_definitions));
      setDefaultsLoaded(true);
    }
  }, [isNewTemplate, defaultVariablesData, defaultsLoaded]);

  // Extract variables from YAML
  const yamlVariables = useMemo(
    () => extractVariablesFromYaml(yamlContent),
    [yamlContent]
  );

  // Validation: check for bidirectional matching between YAML and variables
  const validation = useMemo(() => {
    const errors: string[] = [];
    const warnings: string[] = [];
    const definedVars = new Set(
      variables.map((v) => v.name).filter(Boolean)
    );

    // Check for undefined variables in YAML (YAML has vars not in definitions) → error
    const undefinedVars = yamlVariables.filter((v) => !definedVars.has(v));
    if (undefinedVars.length > 0) {
      errors.push(`YAML 中使用了未定义的变量: ${undefinedVars.join(", ")}`);
    }

    // Check for unused variables (defined but not in YAML) → warning
    const unusedVars = [...definedVars].filter(
      (v) => !yamlVariables.includes(v)
    );
    if (unusedVars.length > 0) {
      warnings.push(`已定义但未在 YAML 中使用的变量: ${unusedVars.join(", ")}`);
    }

    // Check for duplicate variable names → error
    const varNames = variables.map((v) => v.name).filter(Boolean);
    const duplicates = varNames.filter(
      (name, index) => varNames.indexOf(name) !== index
    );
    if (duplicates.length > 0) {
      errors.push(`变量名重复: ${[...new Set(duplicates)].join(", ")}`);
    }

    return { errors, warnings };
  }, [yamlVariables, variables]);

  // Handle variables form change
  const handleVariablesChange = (newVariables: VariableFormData[]) => {
    setVariables(newVariables);
  };

  // Handle compare (only available in edit mode)
  const handleCompare = async () => {
    if (!isEditMode) return;

    try {
      const result = await refetchTemplate();
      if (result.data) {
        originalYamlRef.current = result.data.yaml_template;
        originalVariablesRef.current = result.data.variable_definitions;
      }
      setIsCompareVisible(true);
    } catch {
      message.warning("获取最新配置失败，使用当前缓存的配置进行对比");
      setIsCompareVisible(true);
    }
  };

  // Get current variables in API format for comparison
  const currentApiVariables = convertToApiFormat(variables);

  // Handle save
  const handleSave = async () => {
    try {
      const values = await form.validateFields();

      if (!yamlContent.trim()) {
        message.error("请输入 YAML 模板内容");
        return;
      }

      if (validation.errors.length > 0) {
        message.error("请先修复验证错误");
        return;
      }

      const doSave = async () => {
        // Use the shared conversion function
        const apiVariables = convertToApiFormat(variables);

        if (isEditMode && id) {
          const request: TemplateUpdateRequest = {
            name: values.name,
            description: values.description || undefined,
            yaml_template: yamlContent,
            variable_definitions: apiVariables,
          };
          await updateMutation.mutateAsync({ id: parseInt(id, 10), request });
          navigate("/templates");
        } else {
          const request: TemplateCreateRequest = {
            name: values.name,
            description: values.description || undefined,
            yaml_template: yamlContent,
            variable_definitions: apiVariables,
          };
          await createMutation.mutateAsync(request);
          navigate("/templates");
        }
      };

      if (validation.warnings.length > 0) {
        Modal.confirm({
          title: "存在未使用的变量",
          icon: <ExclamationCircleOutlined />,
          content: (
            <ul className="list-disc pl-4 mt-2">
              {validation.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          ),
          okText: "仍然保存",
          cancelText: "取消",
          onOk: doSave,
        });
      } else {
        await doSave();
      }
    } catch (error) {
      console.error("Save failed:", error);
    }
  };

  if ((isLoading && templateId) || (isNewTemplate && isLoadingDefaults)) {
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

        <Card title="YAML 模板" className="mb-4">
          <div className="space-y-4">
            <Alert
              type="info"
              showIcon
              message="使用 {变量名} 格式定义占位符"
              description={
                <div>
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
        </Card>

        <Card title={`变量定义 (${variables.length})`} className="mb-4">
          <div className="space-y-4">
            <Alert
              type="info"
              showIcon
              message="定义模板变量"
              description="在此定义模板中使用的所有变量。YAML 模板中引用的变量必须在此处都有定义。"
            />

            <VariableDefinitionForm
              value={variables}
              onChange={handleVariablesChange}
              title="自定义变量列表"
            />
          </div>
        </Card>

        {validation.errors.length > 0 && (
          <Alert
            type="error"
            showIcon
            message="验证错误"
            description={
              <ul className="list-disc pl-4">
                {validation.errors.map((error, index) => (
                  <li key={index}>{error}</li>
                ))}
              </ul>
            }
            className="mb-4"
          />
        )}

        {validation.warnings.length > 0 && (
          <Alert
            type="warning"
            showIcon
            message="验证警告"
            description={
              <ul className="list-disc pl-4">
                {validation.warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
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
              {isEditMode && (
                <Button
                  icon={<DiffOutlined />}
                  onClick={handleCompare}
                >
                  差异对比
                </Button>
              )}
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSave}
                loading={createMutation.isPending || updateMutation.isPending}
                disabled={validation.errors.length > 0}
              >
                {isEditMode ? "保存" : "创建"}
              </Button>
            </Space>
          </div>
        </Card>
      </Form>

      {/* Compare Modal */}
      <Modal
        title="模板差异对比"
        open={isCompareVisible}
        onCancel={() => setIsCompareVisible(false)}
        width={1400}
        footer={[
          <Button key="close" onClick={() => setIsCompareVisible(false)}>
            关闭
          </Button>
        ]}
      >
        <div className="space-y-4">
          <Alert
            type="info"
            showIcon
            message="差异对比视图"
            description="左侧为服务器当前配置，右侧为本地编辑的配置。高亮显示的是差异部分。"
          />
          <Tabs
            activeKey={diffTab}
            onChange={setDiffTab}
            items={[
              {
                key: "yaml",
                label: "YAML 模板",
                children: (
                  <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden', height: '500px' }}>
                    <MonacoDiffEditor
                      height="500px"
                      language="yaml"
                      original={originalYamlRef.current}
                      modified={yamlContent}
                      theme="vs-light"
                    />
                  </div>
                ),
              },
              {
                key: "variables",
                label: "变量定义",
                children: (
                  <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden', height: '500px' }}>
                    <MonacoDiffEditor
                      height="500px"
                      language="json"
                      original={JSON.stringify(originalVariablesRef.current, null, 2)}
                      modified={JSON.stringify(currentApiVariables, null, 2)}
                      theme="vs-light"
                    />
                  </div>
                ),
              },
            ]}
          />
        </div>
      </Modal>
    </div>
  );
};

export default TemplateEdit;
