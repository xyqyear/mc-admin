import React, { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Button, Alert, Space, App, Modal } from "antd";
import { ArrowLeftOutlined, SaveOutlined, SettingOutlined, DiffOutlined } from "@ant-design/icons";
import PageHeader from "@/components/layout/PageHeader";
import LoadingSpinner from "@/components/layout/LoadingSpinner";
import { MonacoDiffEditor } from "@/components/editors";
import {
  VariableDefinitionForm,
  convertToFormData,
  convertToApiFormat,
  type VariableFormData,
} from "@/components/templates";
import { useDefaultVariables } from "@/hooks/queries/base/useTemplateQueries";
import { useTemplateMutations } from "@/hooks/mutations/useTemplateMutations";
import type { VariableDefinition } from "@/hooks/api/templateApi";

const DefaultVariables: React.FC = () => {
  const navigate = useNavigate();
  const { message } = App.useApp();

  const { data: defaultVariablesData, isLoading, refetch } = useDefaultVariables();
  const { useUpdateDefaultVariables } = useTemplateMutations();
  const updateMutation = useUpdateDefaultVariables();

  const [variables, setVariables] = useState<VariableFormData[]>([]);
  const [isCompareVisible, setIsCompareVisible] = useState(false);
  // Store original variables for comparison
  const originalVariablesRef = useRef<VariableDefinition[]>([]);

  // Initialize form with loaded data
  useEffect(() => {
    if (defaultVariablesData?.variable_definitions) {
      originalVariablesRef.current = defaultVariablesData.variable_definitions;
      setVariables(convertToFormData(defaultVariablesData.variable_definitions));
    }
  }, [defaultVariablesData]);

  // Check for duplicate variable names
  const duplicateErrors = React.useMemo(() => {
    const varNames = variables.map((v) => v.name).filter(Boolean);
    const duplicates = varNames.filter(
      (name, index) => varNames.indexOf(name) !== index
    );
    if (duplicates.length > 0) {
      return [`变量名重复: ${[...new Set(duplicates)].join(", ")}`];
    }
    return [];
  }, [variables]);

  // Handle compare
  const handleCompare = async () => {
    try {
      const result = await refetch();
      if (result.data?.variable_definitions) {
        originalVariablesRef.current = result.data.variable_definitions;
      }
      setIsCompareVisible(true);
    } catch {
      message.warning("获取最新配置失败，使用当前缓存的配置进行对比");
      setIsCompareVisible(true);
    }
  };

  const handleSave = async () => {
    if (duplicateErrors.length > 0) {
      message.error("请先修复验证错误");
      return;
    }

    const apiVariables = convertToApiFormat(variables);

    await updateMutation.mutateAsync(apiVariables);
  };

  if (isLoading) {
    return <LoadingSpinner />;
  }

  // Get current variables in API format for comparison
  const currentApiVariables = convertToApiFormat(variables);

  return (
    <div className="space-y-4">
      <PageHeader title="默认变量配置" icon={<SettingOutlined />} />

      <Card>
        <Alert
          type="info"
          showIcon
          message="默认变量配置"
          description="这些变量将在创建新模板时自动预填充到变量列表中。填充后与普通变量无异，可以自由修改或删除。"
          className="mb-4"
        />

        <VariableDefinitionForm
          value={variables}
          onChange={setVariables}
          title="默认变量列表"
        />

        {duplicateErrors.length > 0 && (
          <Alert
            type="error"
            showIcon
            title="验证错误"
            description={
              <ul className="list-disc pl-4">
                {duplicateErrors.map((error, index) => (
                  <li key={index}>{error}</li>
                ))}
              </ul>
            }
            className="mt-4"
          />
        )}

        <div className="flex justify-between mt-4">
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
            返回
          </Button>
          <Space>
            <Button
              icon={<DiffOutlined />}
              onClick={handleCompare}
            >
              差异对比
            </Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              onClick={handleSave}
              loading={updateMutation.isPending}
              disabled={duplicateErrors.length > 0}
            >
              保存
            </Button>
          </Space>
        </div>
      </Card>

      {/* Compare Modal */}
      <Modal
        title="配置差异对比"
        open={isCompareVisible}
        onCancel={() => setIsCompareVisible(false)}
        width={1200}
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
            title="差异对比视图"
            description="左侧为服务器当前配置，右侧为本地编辑的配置。高亮显示的是差异部分。"
          />
          <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden', height: '600px' }}>
            <MonacoDiffEditor
              height="600px"
              language="json"
              original={JSON.stringify(originalVariablesRef.current, null, 2)}
              modified={JSON.stringify(currentApiVariables, null, 2)}
              theme="vs-light"
            />
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default DefaultVariables;
