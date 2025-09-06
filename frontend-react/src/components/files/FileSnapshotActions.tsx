import React, { useState } from 'react'
import { Button, Modal, List, Tooltip, message, Space, Tag, Typography, Drawer, Divider } from 'antd'
import { DatabaseOutlined, HistoryOutlined, EyeOutlined } from '@ant-design/icons'
import { useSnapshotMutations } from '@/hooks/mutations/useSnapshotMutations'
import { useSnapshotQueries } from '@/hooks/queries/base/useSnapshotQueries'
import { formatDateTime } from '@/utils/formatUtils'
import { formatUtils } from '@/utils/serverUtils'
import type { FileItem } from '@/types/Server'
import type { Snapshot, RestorePreviewAction } from '@/hooks/api/snapshotApi'

const { Text } = Typography

interface FileSnapshotActionsProps {
  file: FileItem
  serverId: string
}

interface SafetyCheckModalProps {
  open: boolean
  onCancel: () => void
  onCreateAndRestore: () => void
  onContinueWithoutCreate: () => void
  loading?: boolean
}

const SafetyCheckModal: React.FC<SafetyCheckModalProps> = ({
  open,
  onCancel,
  onCreateAndRestore,
  onContinueWithoutCreate,
  loading = false
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
        ⚠️ 检测到该路径在过去1分钟内没有创建快照。
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
  previewLoading
}) => (
  <Modal
    title={`选择要回滚的快照 - ${filePath}`}
    open={open}
    onCancel={onCancel}
    width={700}
    footer={[
      <Button key="cancel" onClick={onCancel}>
        取消
      </Button>
    ]}
  >
    <div className="space-y-4">
      <Text type="secondary">
        以下是包含该路径的所有快照，请选择要回滚的版本：
      </Text>
      
      <List
        loading={loading}
        dataSource={snapshots}
        renderItem={(snapshot) => (
          <List.Item
            actions={[
              <Button
                key="preview"
                icon={<EyeOutlined />}
                size="small"
                onClick={() => onPreview(snapshot.id)}
                loading={previewLoading}
              >
                预览
              </Button>,
              <Button
                key="restore"
                type="primary"
                size="small"
                onClick={() => onRestore(snapshot.id)}
                loading={restoreLoading}
              >
                回滚到此版本
              </Button>
            ]}
          >
            <List.Item.Meta
              title={
                <Space>
                  <Text strong>{snapshot.short_id}</Text>
                  <Tag color="blue">{formatDateTime(snapshot.time)}</Tag>
                </Space>
              }
              description={
                <div className="space-y-1">
                  <Text type="secondary">
                    主机: {snapshot.hostname} | 用户: {snapshot.username}
                  </Text>
                  {snapshot.summary && (
                    <div className="text-xs text-gray-500">
                      文件: +{snapshot.summary.files_new} ~{snapshot.summary.files_changed} 
                      | 大小: {Math.round(snapshot.summary.data_added / 1024 / 1024)}MB
                    </div>
                  )}
                </div>
              }
            />
          </List.Item>
        )}
        locale={{ emptyText: '没有找到包含该路径的快照' }}
      />
    </div>
  </Modal>
)

interface PreviewModalProps {
  open: boolean
  onCancel: () => void
  previewData: RestorePreviewAction[] | null
  previewSummary: string | null
  loading: boolean
  snapshotId: string
}

const PreviewModal: React.FC<PreviewModalProps> = ({
  open,
  onCancel,
  previewData,
  previewSummary,
  loading,
  snapshotId
}) => (
  <Drawer
    title={`预览快照回滚 - ${snapshotId}`}
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
        
        <List
          dataSource={previewData}
          renderItem={(action, index) => (
            <List.Item key={index}>
              <div className="w-full">
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
            </List.Item>
          )}
          locale={{ emptyText: '没有变更' }}
        />
      </div>
    ) : (
      <div className="text-center py-8">
        <Text type="secondary">无法生成预览</Text>
      </div>
    )}
  </Drawer>
)

const FileSnapshotActions: React.FC<FileSnapshotActionsProps> = ({ file, serverId }) => {
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

  // Queries
  const { 
    data: snapshots = [], 
    isLoading: isLoadingSnapshots,
    refetch: refetchSnapshots
  } = useSnapshotsForPath(serverId, file.path)

  const handleBackup = async () => {
    try {
      await createSnapshotMutation.mutateAsync({
        server_id: serverId,
        path: file.path
      })
      message.success(`已为 ${file.name} 创建快照`)
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
        path: file.path
      })
      
      message.success(`已成功回滚 ${file.name}`)
      setIsSnapshotModalVisible(false)
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
        path: file.path
      })
      
      // 然后执行回滚
      await restoreSnapshotMutation.mutateAsync({
        snapshot_id: selectedSnapshotId,
        server_id: serverId,
        path: file.path
      })
      
      message.success(`已创建安全快照并成功回滚 ${file.name}`)
      setIsSafetyCheckVisible(false)
      setSelectedSnapshotId('')
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
        path: file.path
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
        path: file.path,
        skip_safety_check: true  // 关闭安全检查
      })
      
      message.success(`已成功回滚 ${file.name}`)
      setIsSafetyCheckVisible(false)
      setSelectedSnapshotId('')
    } catch (error: any) {
      message.error(`回滚失败: ${error?.message || '未知错误'}`)
    }
  }

  return (
    <>
      <Space size="small">
        <Tooltip title={`为 ${file.name} 创建快照`}>
          <Button
            icon={<DatabaseOutlined />}
            size="small"
            onClick={handleBackup}
            loading={createSnapshotMutation.isPending}
          />
        </Tooltip>
        
        <Tooltip title={`回滚 ${file.name}`}>
          <Button
            icon={<HistoryOutlined />}
            size="small"
            onClick={handleRollback}
          />
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
        filePath={file.path}
        onPreview={handlePreviewRestore}
        previewLoading={previewRestoreMutation.isPending}
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
      />

      {/* 预览Modal */}
      <PreviewModal
        open={isPreviewVisible}
        onCancel={() => setIsPreviewVisible(false)}
        previewData={previewData}
        previewSummary={previewSummary}
        loading={previewRestoreMutation.isPending}
        snapshotId={selectedSnapshotId}
      />
    </>
  )
}

export default FileSnapshotActions