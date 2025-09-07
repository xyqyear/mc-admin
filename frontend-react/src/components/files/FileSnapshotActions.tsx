import React, { useState } from 'react'
import { Button, Modal, Table, Tooltip, message, Space, Tag, Typography, Drawer, Divider, type TableProps } from 'antd'
import { DatabaseOutlined, HistoryOutlined, EyeOutlined } from '@ant-design/icons'
import { useSnapshotMutations } from '@/hooks/mutations/useSnapshotMutations'
import { useSnapshotQueries } from '@/hooks/queries/base/useSnapshotQueries'
import { formatDateTime } from '@/utils/formatUtils'
import { formatUtils } from '@/utils/serverUtils'
import type { FileItem } from '@/types/Server'
import type { Snapshot, RestorePreviewAction } from '@/hooks/api/snapshotApi'

const { Text } = Typography

interface FileSnapshotActionsProps {
  file?: FileItem
  serverId: string
  path?: string
  isServerMode?: boolean
  onRefresh?: () => void
}

interface SafetyCheckModalProps {
  open: boolean
  onCancel: () => void
  onCreateAndRestore: () => void
  onContinueWithoutCreate: () => void
  loading?: boolean
  isServerMode?: boolean
}

const SafetyCheckModal: React.FC<SafetyCheckModalProps> = ({
  open,
  onCancel,
  onCreateAndRestore,
  onContinueWithoutCreate,
  loading = false,
  isServerMode = false
}) => (
  <Modal
    title="安全检查"
    open={open}
    onCancel={onCancel}
    footer={[
      <Button key="cancel" onClick={onCancel}>
        取消
      </Button>,
      <Button 
        key="continue" 
        type="default" 
        danger
        onClick={onContinueWithoutCreate}
        loading={loading}
      >
        继续回滚
      </Button>,
      <Button 
        key="create" 
        type="primary" 
        onClick={onCreateAndRestore}
        loading={loading}
      >
        创建快照并回滚
      </Button>,
    ]}
  >
    <div className="space-y-4">
      <Text type="warning">
        ⚠️ 检测到{isServerMode ? '整个服务器' : '该路径'}在过去1分钟内没有创建快照。
      </Text>
      <Text>
        为了安全起见，建议您在回滚前先创建一个当前状态的快照。
      </Text>
      <div className="bg-gray-50 p-3 rounded">
        <Text type="secondary">
          您可以选择：
        </Text>
        <ul className="mt-2 ml-4">
          <li>创建快照并回滚：安全选项，创建备份后再执行回滚</li>
          <li>继续回滚：直接执行回滚，不创建备份</li>
        </ul>
      </div>
    </div>
  </Modal>
)

interface SnapshotSelectionModalProps {
  open: boolean
  onCancel: () => void
  snapshots: Snapshot[]
  loading: boolean
  onRestore: (snapshotId: string) => void
  restoreLoading: boolean
  filePath: string
  onPreview: (snapshotId: string) => void
  previewLoading: boolean
  isServerMode?: boolean
}

const SnapshotSelectionModal: React.FC<SnapshotSelectionModalProps> = ({
  open,
  onCancel,
  snapshots,
  loading,
  onRestore,
  restoreLoading,
  filePath,
  onPreview,
  previewLoading,
  isServerMode = false
}) => {
  const columns: TableProps<Snapshot>['columns'] = [
    {
      title: '快照ID',
      dataIndex: 'short_id',
      key: 'short_id',
      width: 100,
      render: (shortId: string, record: Snapshot) => (
        <Tooltip title={`完整ID: ${record.id}`}>
          <Tag color="blue" className="font-mono">
            {shortId}
          </Tag>
        </Tooltip>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'time',
      key: 'time',
      width: 180,
      render: (time: string) => (
        <Text className="font-mono text-sm">
          {formatDateTime(time)}
        </Text>
      ),
      sorter: (a, b) => new Date(a.time).getTime() - new Date(b.time).getTime(),
      defaultSortOrder: 'descend',
    },
    {
      title: '用户',
      dataIndex: 'username',
      key: 'username',
      width: 120,
      render: (username: string) => (
        <Text className="text-sm">{username}</Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_: any, record: Snapshot) => (
        <Space size="small">
          <Button
            icon={<EyeOutlined />}
            size="small"
            onClick={() => onPreview(record.id)}
            loading={previewLoading}
          >
            预览
          </Button>
          <Button
            type="primary"
            size="small"
            onClick={() => onRestore(record.id)}
            loading={restoreLoading}
          >
            回滚
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <Modal
      title={`选择要回滚的快照 - ${isServerMode ? '整个服务器' : filePath}`}
      open={open}
      onCancel={onCancel}
      width={800}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          取消
        </Button>
      ]}
    >
      <div className="space-y-4">
        <Text type="secondary">
          以下是包含{isServerMode ? '整个服务器' : '该路径'}的所有快照，请选择要回滚的版本：
        </Text>
        
        <Table<Snapshot>
          columns={columns}
          dataSource={snapshots}
          rowKey="id"
          loading={loading}
          pagination={false}
          size="small"
          locale={{ emptyText: `没有找到包含${isServerMode ? '整个服务器' : '该路径'}的快照` }}
        />
      </div>
    </Modal>
  )
}

interface PreviewModalProps {
  open: boolean
  onCancel: () => void
  previewData: RestorePreviewAction[] | null
  previewSummary: string | null
  loading: boolean
  snapshotId: string
  isServerMode?: boolean
}

const PreviewModal: React.FC<PreviewModalProps> = ({
  open,
  onCancel,
  previewData,
  previewSummary,
  loading,
  snapshotId,
  isServerMode = false
}) => (
  <Drawer
    title={`预览${isServerMode ? '服务器' : ''}快照回滚 - ${snapshotId}`}
    open={open}
    onClose={onCancel}
    width={800}
    placement="right"
  >
    {loading ? (
      <div className="text-center py-8">
        <Text>正在生成预览...</Text>
      </div>
    ) : previewData ? (
      <div className="space-y-4">
        {previewSummary && (
          <div className="bg-blue-50 p-3 rounded">
            <Text strong>{previewSummary}</Text>
          </div>
        )}
        
        <Divider>详细变更列表</Divider>
        
        <div className="space-y-2">
          {previewData.map((action, index) => (
            <div key={index} className="p-3 border border-gray-200 rounded bg-gray-50">
              <div className="flex items-center space-x-2">
                <Tag color={
                  action.action === 'updated' ? 'orange' :
                  action.action === 'deleted' ? 'red' :
                  action.action === 'restored' ? 'green' : 'blue'
                }>
                  {action.action === 'updated' ? '更新' :
                   action.action === 'deleted' ? '删除' :
                   action.action === 'restored' ? '恢复' :
                   action.action || action.message_type}
                </Tag>
                <Text className="font-mono text-xs">{action.item}</Text>
                {action.action !== 'deleted' && action.size && (
                  <Text type="secondary" className="text-xs">
                    ({formatUtils.formatBytes(action.size)})
                  </Text>
                )}
              </div>
            </div>
          ))}
          {previewData.length === 0 && (
            <div className="text-center py-8">
              <Text type="secondary">没有变更</Text>
            </div>
          )}
        </div>
      </div>
    ) : (
      <div className="text-center py-8">
        <Text type="secondary">无法生成预览</Text>
      </div>
    )}
  </Drawer>
)

const FileSnapshotActions: React.FC<FileSnapshotActionsProps> = ({ 
  file, 
  serverId, 
  path, 
  isServerMode = false,
  onRefresh 
}) => {
  const [isSnapshotModalVisible, setIsSnapshotModalVisible] = useState(false)
  const [isSafetyCheckVisible, setIsSafetyCheckVisible] = useState(false)
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string>('')
  const [isPreviewVisible, setIsPreviewVisible] = useState(false)
  const [previewData, setPreviewData] = useState<RestorePreviewAction[] | null>(null)
  const [previewSummary, setPreviewSummary] = useState<string | null>(null)

  // Hooks
  const { useCreateSnapshot, useRestoreSnapshot, usePreviewRestore } = useSnapshotMutations()
  const { useSnapshotsForPath } = useSnapshotQueries()

  // Mutations
  const createSnapshotMutation = useCreateSnapshot()
  const restoreSnapshotMutation = useRestoreSnapshot()
  const previewRestoreMutation = usePreviewRestore()

  // 确定实际的路径和文件名
  const actualPath = path || file?.path || '/'
  const displayName = isServerMode ? '整个服务器' : (file?.name || '服务器')

  // Queries - 默认禁用自动查询，只有用户点击回滚按钮时才请求数据
  const { 
    data: snapshots = [], 
    isLoading: isLoadingSnapshots,
    refetch: refetchSnapshots
  } = useSnapshotsForPath(serverId, actualPath, false)

  const handleBackup = async () => {
    try {
      await createSnapshotMutation.mutateAsync({
        server_id: serverId,
        path: actualPath
      })
      message.success(`已为 ${displayName} 创建快照`)
    } catch (error) {
      message.error(`创建快照失败: ${error}`)
    }
  }

  const handleRollback = () => {
    // 刷新快照列表并打开选择modal
    refetchSnapshots()
    setIsSnapshotModalVisible(true)
  }

  const handleSnapshotRestore = async (snapshotId: string) => {
    setSelectedSnapshotId(snapshotId)
    
    try {
      // 首先尝试直接回滚，后端会检查安全性
      await restoreSnapshotMutation.mutateAsync({
        snapshot_id: snapshotId,
        server_id: serverId,
        path: actualPath
      })
      
      message.success(`已成功回滚 ${displayName}`)
      setIsSnapshotModalVisible(false)
      // 如果有刷新回调，执行刷新
      onRefresh?.()
    } catch (error: any) {
      // 检查是否是安全检查错误
      if (error?.message?.includes('no recent snapshot') || error?.message?.includes('1 minute')) {
        // 显示安全检查对话框
        setIsSnapshotModalVisible(false)
        setIsSafetyCheckVisible(true)
      } else {
        message.error(`回滚失败: ${error?.message || '未知错误'}`)
      }
    }
  }

  const handleCreateAndRestore = async () => {
    try {
      // 先创建快照
      await createSnapshotMutation.mutateAsync({
        server_id: serverId,
        path: actualPath
      })
      
      // 然后执行回滚
      await restoreSnapshotMutation.mutateAsync({
        snapshot_id: selectedSnapshotId,
        server_id: serverId,
        path: actualPath
      })
      
      message.success(`已创建安全快照并成功回滚 ${displayName}`)
      setIsSafetyCheckVisible(false)
      setSelectedSnapshotId('')
      // 如果有刷新回调，执行刷新
      onRefresh?.()
    } catch (error: any) {
      message.error(`操作失败: ${error?.message || '未知错误'}`)
    }
  }

  const handlePreviewRestore = async (snapshotId: string) => {
    try {
      setSelectedSnapshotId(snapshotId)
      setPreviewData(null)
      setPreviewSummary(null)
      setIsPreviewVisible(true)
      
      const previewResult = await previewRestoreMutation.mutateAsync({
        snapshot_id: snapshotId,
        server_id: serverId,
        path: actualPath
      })
      
      setPreviewData(previewResult.actions)
      setPreviewSummary(previewResult.preview_summary)
    } catch (error: any) {
      message.error(`预览失败: ${error?.message || '未知错误'}`)
      setIsPreviewVisible(false)
    }
  }

  const handleContinueWithoutCreate = async () => {
    try {
      // 跳过安全检查强制执行回滚
      await restoreSnapshotMutation.mutateAsync({
        snapshot_id: selectedSnapshotId,
        server_id: serverId,
        path: actualPath,
        skip_safety_check: true  // 关闭安全检查
      })
      
      message.success(`已成功回滚 ${displayName}`)
      setIsSafetyCheckVisible(false)
      setSelectedSnapshotId('')
      // 如果有刷新回调，执行刷新
      onRefresh?.()
    } catch (error: any) {
      message.error(`回滚失败: ${error?.message || '未知错误'}`)
    }
  }

  return (
    <>
      <Space size="small">
        <Tooltip title={`为 ${displayName} 创建快照`}>
          <Button
            icon={<DatabaseOutlined />}
            size={isServerMode ? "middle" : "small"}
            onClick={handleBackup}
            loading={createSnapshotMutation.isPending}
          >
            {isServerMode ? '创建快照' : ''}
          </Button>
        </Tooltip>
        
        <Tooltip title={`回滚 ${displayName}`}>
          <Button
            icon={<HistoryOutlined />}
            size={isServerMode ? "middle" : "small"}
            type={isServerMode ? "primary" : "default"}
            onClick={handleRollback}
          >
            {isServerMode ? '快照回滚' : ''}
          </Button>
        </Tooltip>
      </Space>

      {/* 快照选择Modal */}
      <SnapshotSelectionModal
        open={isSnapshotModalVisible}
        onCancel={() => setIsSnapshotModalVisible(false)}
        snapshots={snapshots}
        loading={isLoadingSnapshots}
        onRestore={handleSnapshotRestore}
        restoreLoading={restoreSnapshotMutation.isPending}
        filePath={actualPath}
        onPreview={handlePreviewRestore}
        previewLoading={previewRestoreMutation.isPending}
        isServerMode={isServerMode}
      />

      {/* 安全检查Modal */}
      <SafetyCheckModal
        open={isSafetyCheckVisible}
        onCancel={() => {
          setIsSafetyCheckVisible(false)
          setSelectedSnapshotId('')
        }}
        onCreateAndRestore={handleCreateAndRestore}
        onContinueWithoutCreate={handleContinueWithoutCreate}
        loading={createSnapshotMutation.isPending || restoreSnapshotMutation.isPending}
        isServerMode={isServerMode}
      />

      {/* 预览Modal */}
      <PreviewModal
        open={isPreviewVisible}
        onCancel={() => setIsPreviewVisible(false)}
        previewData={previewData}
        previewSummary={previewSummary}
        loading={previewRestoreMutation.isPending}
        snapshotId={selectedSnapshotId}
        isServerMode={isServerMode}
      />
    </>
  )
}

export default FileSnapshotActions