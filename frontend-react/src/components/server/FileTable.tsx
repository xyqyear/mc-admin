import React from 'react'
import { Table, Button, Space, Tooltip, Dropdown, Popconfirm } from 'antd'
import {
  DeleteOutlined,
  DownloadOutlined,
  MoreOutlined,
  FileZipOutlined
} from '@ant-design/icons'
import { isFileEditable } from '@/config/fileEditingConfig'
import { formatFileSize, formatDate } from '@/utils/formatUtils'
import FileIcon from '@/components/files/FileIcon'
import FileSnapshotActions from '@/components/files/FileSnapshotActions'
import type { FileItem } from '@/types/Server'
import type { SortOrder, ColumnType } from 'antd/es/table/interface'

interface FileTableProps {
  fileData?: { items: FileItem[] }
  isLoadingFiles: boolean
  selectedFiles: string[]
  setSelectedFiles: (files: string[]) => void
  currentPage: number
  pageSize: number
  setCurrentPage: (page: number) => void
  setPageSize: (size: number) => void
  serverId: string
  onFileEdit: (file: FileItem) => void
  onFileDelete: (file: FileItem) => void
  onFileDownload: (file: FileItem) => void
  onFileRename: (file: FileItem) => void
  onFolderOpen: (file: FileItem) => void
  onFileCompress: (file: FileItem) => void
  createArchiveMutation: { isPending: boolean }
}

const FileTable: React.FC<FileTableProps> = ({
  fileData,
  isLoadingFiles,
  selectedFiles,
  setSelectedFiles,
  currentPage,
  pageSize,
  setCurrentPage,
  setPageSize,
  serverId,
  onFileEdit,
  onFileDelete,
  onFileDownload,
  onFileRename,
  onFolderOpen,
  onFileCompress,
  createArchiveMutation
}) => {
  const moreActions = (file: FileItem) => [
    {
      key: 'rename',
      label: '重命名',
      onClick: () => onFileRename(file)
    }
  ]

  const columns: ColumnType<FileItem>[] = [
    {
      title: '文件名',
      dataIndex: 'name',
      key: 'name',
      sorter: (a: FileItem, b: FileItem) => {
        // Custom sorting: directories first, then files, both alphabetically
        if (a.type !== b.type) {
          return a.type === 'directory' ? -1 : 1
        }
        return a.name.localeCompare(b.name, 'zh-CN', { sensitivity: 'base' })
      },
      sortDirections: ['ascend', 'descend'] as SortOrder[],
      defaultSortOrder: 'ascend' as SortOrder,
      render: (name: string, file: FileItem) => {
        const isEditable = isFileEditable(file.name)
        const isDirectory = file.type === 'directory'

        return (
          <div className="flex items-center space-x-2">
            <FileIcon file={file} />
            <Tooltip
              title={
                isDirectory ? '点击打开文件夹' :
                  isEditable ? '点击编辑文件' :
                    undefined
              }
            >
              <span
                className={
                  isDirectory ? 'font-medium cursor-pointer hover:text-blue-600' :
                    isEditable ? 'font-medium cursor-pointer text-blue-600 hover:text-blue-800' :
                      'font-medium'
                }
                onClick={() => {
                  if (isDirectory) {
                    onFolderOpen(file)
                  } else if (isEditable) {
                    onFileEdit(file)
                  }
                }}
              >
                {name}
              </span>
            </Tooltip>
          </div>
        )
      },
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      width: 90,
      sorter: (a: FileItem, b: FileItem) => a.size - b.size,
      sortDirections: ['ascend', 'descend'] as SortOrder[],
      render: (size: number) => formatFileSize(size),
    },
    {
      title: '修改时间',
      dataIndex: 'modified_at',
      key: 'modified_at',
      width: 150,
      sorter: (a: FileItem, b: FileItem) => a.modified_at - b.modified_at,
      sortDirections: ['ascend', 'descend'] as SortOrder[],
      render: (timestamp: number) => formatDate(timestamp),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, file: FileItem) => (
        <Space size="small">
          <FileSnapshotActions file={file} serverId={serverId} />

          <Tooltip title="下载">
            <Button
              icon={<DownloadOutlined />}
              size="small"
              onClick={() => onFileDownload(file)}
            />
          </Tooltip>
          <Tooltip title="压缩">
            <Button
              icon={<FileZipOutlined />}
              size="small"
              onClick={() => onFileCompress(file)}
              loading={createArchiveMutation.isPending}
            />
          </Tooltip>
          <Dropdown
            menu={{
              items: moreActions(file).map(action => ({
                ...action,
                onClick: action.onClick
              }))
            }}
            trigger={['click']}
          >
            <Button size="small" icon={<MoreOutlined />} />
          </Dropdown>
          <Popconfirm
            title="确定要删除这个文件吗？"
            onConfirm={() => onFileDelete(file)}
            okText="确定"
            cancelText="取消"
          >
            <Button
              icon={<DeleteOutlined />}
              size="small"
              danger
            />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Table
      dataSource={fileData?.items || []}
      columns={columns}
      rowKey="path"
      size="small"
      loading={isLoadingFiles}
      rowSelection={{
        selectedRowKeys: selectedFiles,
        onChange: (selectedRowKeys: React.Key[]) => {
          setSelectedFiles(selectedRowKeys as string[])
        },
        getCheckboxProps: (record: FileItem) => ({
          name: record.name,
        }),
      }}
      pagination={{
        current: currentPage,
        pageSize: pageSize,
        showSizeChanger: true,
        showQuickJumper: true,
        pageSizeOptions: ['10', '20', '50', '100'],
        showTotal: (total, range) => `${range[0]}-${range[1]} 共 ${total} 个文件`,
        simple: false,
        size: "default",
        onChange: (page, size) => {
          setCurrentPage(page)
          if (size !== pageSize) {
            setPageSize(size)
            setCurrentPage(1) // Reset to first page when page size changes
          }
        },
        onShowSizeChange: (_, size) => {
          setPageSize(size)
          setCurrentPage(1) // Reset to first page when page size changes
        }
      }}
      onRow={(record) => ({
        onDoubleClick: () => {
          if (record.type === 'directory') {
            onFolderOpen(record)
          }
        }
      })}
    />
  )
}

export default FileTable