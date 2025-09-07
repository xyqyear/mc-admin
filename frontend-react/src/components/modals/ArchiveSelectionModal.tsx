import React, { useState } from 'react'
import {
  Modal,
  Table,
  Button,
  Alert,
} from 'antd'
import {
  FileZipOutlined,
  FileOutlined,
  FolderOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useArchiveQueries } from '@/hooks/queries/base/useArchiveQueries'
import { formatFileSize, formatDate } from '@/utils/formatUtils'
import type { ArchiveFileItem } from '@/hooks/api/archiveApi'
import type { ColumnType, SortOrder } from 'antd/es/table/interface'

interface ArchiveSelectionModalProps {
  open: boolean
  onCancel: () => void
  onSelect: (filename: string) => void
  title?: string
  description?: string
  selectButtonText?: string
  selectButtonType?: 'primary' | 'danger'
}

const ArchiveSelectionModal: React.FC<ArchiveSelectionModalProps> = ({
  open,
  onCancel,
  onSelect,
  title = "选择压缩包文件",
  description = "请选择要使用的压缩包文件来创建服务器",
  selectButtonText = "选择文件",
  selectButtonType = "primary"
}) => {
  const navigate = useNavigate()
  const { useArchiveFileList } = useArchiveQueries()
  const { data: fileData, isLoading } = useArchiveFileList('/', open)

  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [pageSize, setPageSize] = useState(20)
  const [currentPage, setCurrentPage] = useState(1)

  // 过滤出压缩包文件
  const archiveFiles = (fileData?.items || []).filter(file => {
    const isArchive = file.name.toLowerCase().endsWith('.zip') ||
      file.name.toLowerCase().endsWith('.7z')
    return file.type === 'file' && isArchive
  })

  const handleSelect = () => {
    if (selectedFile) {
      onSelect(selectedFile)
    }
  }

  const handleCancel = () => {
    setSelectedFile(null)
    onCancel()
  }

  const handleGoToArchives = () => {
    navigate('/archives')
    handleCancel()
  }

  // Table columns
  const columns: ColumnType<ArchiveFileItem>[] = [
    {
      title: '文件名',
      dataIndex: 'name',
      key: 'name',
      sorter: (a: ArchiveFileItem, b: ArchiveFileItem) =>
        a.name.localeCompare(b.name, 'zh-CN', { sensitivity: 'base' }),
      sortDirections: ['ascend', 'descend'] as SortOrder[],
      render: (name: string) => {
        const isZip = name.toLowerCase().endsWith('.zip')
        const is7z = name.toLowerCase().endsWith('.7z')

        return (
          <div className="flex items-center space-x-2">
            {isZip || is7z ? (
              <FileZipOutlined style={{ color: '#faad14' }} />
            ) : (
              <FileOutlined style={{ color: '#52c41a' }} />
            )}
            <span className="font-medium">{name}</span>
          </div>
        )
      },
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      width: 120,
      sorter: (a: ArchiveFileItem, b: ArchiveFileItem) => a.size - b.size,
      sortDirections: ['ascend', 'descend'] as SortOrder[],
      render: (size: number) => formatFileSize(size),
    },
    {
      title: '修改时间',
      dataIndex: 'modified_at',
      key: 'modified_at',
      width: 180,
      sorter: (a: ArchiveFileItem, b: ArchiveFileItem) => a.modified_at - b.modified_at,
      sortDirections: ['ascend', 'descend'] as SortOrder[],
      defaultSortOrder: 'descend' as SortOrder,
      render: (modified_at: number) => formatDate(modified_at),
    },
  ]

  return (
    <Modal
      title={
        <div className="flex items-center space-x-2">
          <FileZipOutlined />
          <span>{title}</span>
        </div>
      }
      open={open}
      onCancel={handleCancel}
      width={800}
      footer={[
        <Button 
          key="archives" 
          icon={<FolderOutlined />}
          onClick={handleGoToArchives}
        >
          压缩包管理
        </Button>,
        <Button key="cancel" onClick={handleCancel}>
          取消
        </Button>,
        <Button
          key="select"
          type={selectButtonType === 'danger' ? 'primary' : selectButtonType}
          danger={selectButtonType === 'danger'}
          disabled={!selectedFile}
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

        {archiveFiles.length === 0 && !isLoading && (
          <Alert
            message="未找到压缩包文件"
            description="没有找到可用的 .zip 或 .7z 压缩包文件。请先上传压缩包文件到归档管理。"
            type="warning"
            showIcon
          />
        )}

        <Table
          dataSource={archiveFiles}
          columns={columns}
          rowKey="path"
          size="small"
          loading={isLoading}
          rowSelection={{
            type: 'radio',
            selectedRowKeys: selectedFile ? [selectedFile] : [],
            onChange: (selectedRowKeys: React.Key[]) => {
              setSelectedFile(selectedRowKeys[0] as string || null)
            },
            getCheckboxProps: (record: ArchiveFileItem) => ({
              name: record.name,
            }),
          }}
          pagination={{
            current: currentPage,
            pageSize: pageSize,
            showSizeChanger: true,
            showQuickJumper: true,
            pageSizeOptions: ['10', '20', '50'],
            showTotal: (total, range) => `${range[0]}-${range[1]} 共 ${total} 个文件`,
            simple: false,
            size: "default",
            onChange: (page, size) => {
              setCurrentPage(page)
              if (size !== pageSize) {
                setPageSize(size)
                setCurrentPage(1)
              }
            },
            onShowSizeChange: (_, size) => {
              setPageSize(size)
              setCurrentPage(1)
            }
          }}
          locale={{
            emptyText: isLoading ? '加载中...' : '暂无压缩包文件'
          }}
        />

        {selectedFile && (
          <Alert
            message={`已选择文件: ${selectedFile}`}
            type="success"
            showIcon
          />
        )}
      </div>
    </Modal>
  )
}

export default ArchiveSelectionModal