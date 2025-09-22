import React, { useState } from 'react'
import {
  Modal,
  Table,
  Button,
  Alert,
} from 'antd'
import {
  CopyOutlined,
  EyeOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { useServerQueries } from '@/hooks/queries/base/useServerQueries'
import type { ServerListItem } from '@/hooks/api/serverApi'
import type { ColumnType } from 'antd/es/table/interface'

interface ServerTemplateModalProps {
  open: boolean
  onCancel: () => void
  onSelect: (composeContent: string) => void
  title?: string
  description?: string
  selectButtonText?: string
}

const ServerTemplateModal: React.FC<ServerTemplateModalProps> = ({
  open,
  onCancel,
  onSelect,
  title = "选择服务器模板",
  description = "选择现有服务器作为模板，使用其 Docker Compose 配置创建新服务器",
  selectButtonText = "使用模板"
}) => {
  const { useServers, useComposeFile } = useServerQueries()
  const { data: servers, isLoading: serversLoading } = useServers({
    enabled: open
  })

  const [selectedServer, setSelectedServer] = useState<ServerListItem | null>(null)
  const [previewModalVisible, setPreviewModalVisible] = useState(false)

  // 获取选中服务器的Compose文件内容
  const { data: composeContent, isLoading: composeLoading } = useComposeFile(
    selectedServer?.id || '',
    { enabled: !!selectedServer }
  )

  const handleSelect = () => {
    if (selectedServer && composeContent) {
      onSelect(composeContent)
    }
  }

  const handleCancel = () => {
    setSelectedServer(null)
    setPreviewModalVisible(false)
    onCancel()
  }

  const handlePreview = (server: ServerListItem) => {
    setSelectedServer(server)
    setPreviewModalVisible(true)
  }

  const handlePreviewCancel = () => {
    setPreviewModalVisible(false)
  }

  // Table columns
  const columns: ColumnType<ServerListItem>[] = [
    {
      title: '服务器名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => (
        <div className="flex items-center space-x-2">
          <SettingOutlined style={{ color: '#1677ff' }} />
          <span className="font-medium">{name}</span>
        </div>
      ),
    },
    {
      title: '服务器类型',
      dataIndex: 'serverType',
      key: 'serverType',
      width: 120,
      render: (serverType: string) => (
        <span className="uppercase text-sm">{serverType}</span>
      ),
    },
    {
      title: 'Java版本',
      dataIndex: 'javaVersion',
      key: 'javaVersion',
      width: 100,
      render: (javaVersion: number) => (
        <span className="text-sm">Java {javaVersion}</span>
      ),
    },
    {
      title: '游戏版本',
      dataIndex: 'gameVersion',
      key: 'gameVersion',
      width: 120,
      render: (gameVersion: string) => (
        <span className="text-sm">{gameVersion}</span>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_, server: ServerListItem) => (
        <Button
          icon={<EyeOutlined />}
          size="small"
          onClick={() => handlePreview(server)}
          title="预览配置"
        >
          预览
        </Button>
      ),
    },
  ]

  return (
    <>
      <Modal
        title={
          <div className="flex items-center space-x-2">
            <CopyOutlined />
            <span>{title}</span>
          </div>
        }
        open={open}
        onCancel={handleCancel}
        width={900}
        footer={[
          <Button key="cancel" onClick={handleCancel}>
            取消
          </Button>,
          <Button
            key="select"
            type="primary"
            disabled={!selectedServer || composeLoading}
            loading={composeLoading}
            onClick={handleSelect}
          >
            {selectButtonText}
          </Button>
        ]}
      >
        <div className="space-y-4">
          <Alert
            message={description}
            type="info"
            showIcon
          />

          {servers && servers.length === 0 && !serversLoading && (
            <Alert
              message="暂无可用服务器"
              description="没有找到可以作为模板的服务器。请先创建一个服务器后再使用模板功能。"
              type="warning"
              showIcon
            />
          )}

          <Table
            dataSource={servers}
            columns={columns}
            rowKey="id"
            size="small"
            loading={serversLoading}
            rowSelection={{
              type: 'radio',
              selectedRowKeys: selectedServer ? [selectedServer.id] : [],
              onChange: (_: React.Key[], selectedRows: ServerListItem[]) => {
                setSelectedServer(selectedRows[0] || null)
              },
              getCheckboxProps: (record: ServerListItem) => ({
                name: record.name,
              }),
            }}
            pagination={{
              showSizeChanger: true,
              showQuickJumper: true,
              pageSizeOptions: ['10', '20', '50'],
              showTotal: (total, range) => `${range[0]}-${range[1]} 共 ${total} 个服务器`,
              size: "default",
            }}
            locale={{
              emptyText: serversLoading ? '加载中...' : '暂无服务器'
            }}
          />

          {selectedServer && (
            <Alert
              message={`已选择服务器: ${selectedServer.name}`}
              description={`将使用该服务器的 Docker Compose 配置作为模板创建新服务器`}
              type="success"
              showIcon
            />
          )}
        </div>
      </Modal>

      {/* 配置预览Modal */}
      <Modal
        title={
          <div className="flex items-center space-x-2">
            <EyeOutlined />
            <span>预览 Docker Compose 配置</span>
            {selectedServer && <span className="text-gray-500">- {selectedServer.name}</span>}
          </div>
        }
        open={previewModalVisible}
        onCancel={handlePreviewCancel}
        width={800}
        footer={[
          <Button key="close" onClick={handlePreviewCancel}>
            关闭
          </Button>,
          <Button
            key="use"
            type="primary"
            disabled={!composeContent || composeLoading}
            loading={composeLoading}
            onClick={() => {
              setPreviewModalVisible(false)
              handleSelect()
            }}
          >
            使用此模板
          </Button>
        ]}
      >
        <div className="space-y-4">
          {selectedServer && (
            <Alert
              message={`服务器信息: ${selectedServer.name}`}
              description={`类型: ${selectedServer.serverType} | 游戏版本: ${selectedServer.gameVersion} | 端口: ${selectedServer.gamePort}`}
              type="info"
              showIcon
            />
          )}

          {composeLoading ? (
            <div className="text-center py-8">
              <span>正在加载配置文件...</span>
            </div>
          ) : composeContent ? (
            <div className="bg-gray-50 p-4 rounded border">
              <pre className="text-sm overflow-auto max-h-96 whitespace-pre-wrap">
                {composeContent}
              </pre>
            </div>
          ) : (
            <Alert
              message="无法加载配置文件"
              description="该服务器的 Docker Compose 配置文件不存在或无法访问。"
              type="warning"
              showIcon
            />
          )}
        </div>
      </Modal>
    </>
  )
}

export default ServerTemplateModal