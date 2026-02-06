import React from "react";
import { useNavigate } from "react-router-dom";
import {
  Card,
  Button,
  Table,
  App,
  Empty,
  Space,
  Typography,
  Tooltip,
} from "antd";
import {
  PlusOutlined,
  ReloadOutlined,
  SnippetsOutlined,
  EditOutlined,
  DeleteOutlined,
  CopyOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import type { TableProps } from "antd";
import PageHeader from "@/components/layout/PageHeader";
import { useTemplates } from "@/hooks/queries/base/useTemplateQueries";
import { useTemplateMutations } from "@/hooks/mutations/useTemplateMutations";
import type { TemplateListItem } from "@/hooks/api/templateApi";

const { Text } = Typography;

const TemplateList: React.FC = () => {
  const navigate = useNavigate();
  const { modal } = App.useApp();

  const {
    data: templates = [],
    isLoading,
    error,
    refetch,
  } = useTemplates();

  const { useDeleteTemplate } = useTemplateMutations();
  const deleteMutation = useDeleteTemplate();

  const handleCreate = () => {
    navigate("/templates/new");
  };

  const handleCopyCreate = (templateId: number) => {
    navigate(`/templates/new?copyFrom=${templateId}`);
  };

  const handleEdit = (templateId: number) => {
    navigate(`/templates/${templateId}/edit`);
  };

  const handleDelete = (template: TemplateListItem) => {
    modal.confirm({
      title: "删除模板",
      content: `确定要删除模板 "${template.name}" 吗？此操作不可恢复。`,
      okText: "确认删除",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        await deleteMutation.mutateAsync(template.id);
      },
    });
  };

  const columns: TableProps<TemplateListItem>["columns"] = [
    {
      title: "模板名称",
      dataIndex: "name",
      key: "name",
      render: (name: string) => <Text strong>{name}</Text>,
    },
    {
      title: "描述",
      dataIndex: "description",
      key: "description",
      render: (description: string | undefined) => (
        <Text type="secondary">{description || "-"}</Text>
      ),
    },
    {
      title: "变量数量",
      dataIndex: "variable_count",
      key: "variable_count",
      width: 120,
      align: "center",
      render: (count: number) => <Text>{count}</Text>,
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      key: "created_at",
      width: 180,
      render: (date: string) => (
        <Text type="secondary">
          {new Date(date).toLocaleString("zh-CN")}
        </Text>
      ),
    },
    {
      title: "操作",
      key: "actions",
      width: 200,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="编辑">
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record.id)}
            />
          </Tooltip>
          <Tooltip title="复制创建">
            <Button
              type="text"
              icon={<CopyOutlined />}
              onClick={() => handleCopyCreate(record.id)}
            />
          </Tooltip>
          <Tooltip title="删除">
            <Button
              type="text"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(record)}
              loading={deleteMutation.isPending}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <PageHeader title="服务器模板" icon={<SnippetsOutlined />} />

      <Card>
        <div className="flex justify-between items-center mb-4">
          <Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleCreate}
            >
              新建模板
            </Button>
            <Button
              icon={<SettingOutlined />}
              onClick={() => navigate("/templates/default-variables")}
            >
              默认变量配置
            </Button>
            <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
              刷新
            </Button>
          </Space>
        </div>

        {error ? (
          <Empty description={`加载失败: ${error.message}`} />
        ) : (
          <Table
            columns={columns}
            dataSource={templates}
            rowKey="id"
            loading={isLoading}
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 个模板`,
            }}
            locale={{
              emptyText: (
                <Empty
                  description="暂无模板"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                >
                  <Button type="primary" onClick={handleCreate}>
                    创建第一个模板
                  </Button>
                </Empty>
              ),
            }}
          />
        )}
      </Card>
    </div>
  );
};

export default TemplateList;
