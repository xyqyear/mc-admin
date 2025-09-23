import React, { useState } from 'react'
import { Card, Button, Tree, Space } from 'antd'
import { ExpandOutlined, CompressOutlined } from '@ant-design/icons'
import type { DataNode } from 'antd/es/tree'
import FileIcon from '@/components/files/FileIcon'
import type { FileItem } from '@/types/Server'

interface FileUploadTreeProps {
  files: File[]
  title?: string
}

const FileUploadTree: React.FC<FileUploadTreeProps> = ({
  files,
  title = "待上传文件"
}) => {
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([])

  // 格式化文件大小
  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }

  // 将File转换为FileItem格式以便使用FileIcon
  const fileToFileItem = (file: File, fileName: string, filePath: string): FileItem => ({
    name: fileName,
    path: filePath,
    type: 'file',
    size: file.size,
    modified_at: file.lastModified / 1000 // 转换为秒级时间戳
  })

  // 将文件列表转换为Tree数据结构
  const buildTreeData = (files: File[]): DataNode[] => {
    const nodeMap: Record<string, DataNode> = {}
    const rootNodes: DataNode[] = []

    files.forEach((file) => {
      const relativePath = (file as any).webkitRelativePath || file.name
      const pathParts = relativePath.split('/')

      let currentPath = ''

      pathParts.forEach((part: string, partIndex: number) => {
        const parentPath = currentPath
        currentPath += (currentPath ? '/' : '') + part
        const isLastPart = partIndex === pathParts.length - 1

        // 如果节点不存在，创建它
        if (!nodeMap[currentPath]) {
          const node: DataNode = {
            key: currentPath,
            title: isLastPart ? (
              <span>
                <span style={{ marginRight: 8 }}>
                  <FileIcon file={fileToFileItem(file, part, currentPath)} />
                </span>
                {part} <span style={{ color: '#999', fontSize: '12px' }}>({formatFileSize(file.size)})</span>
              </span>
            ) : (
              <span>
                <span style={{ marginRight: 8 }}>
                  <FileIcon file={{ name: part, path: currentPath, type: 'directory', size: 0, modified_at: Date.now() / 1000 }} />
                </span>
                {part}
              </span>
            ),
            children: isLastPart ? undefined : [],
            isLeaf: isLastPart
          }

          nodeMap[currentPath] = node

          // 添加到父节点或根节点
          if (parentPath && nodeMap[parentPath]) {
            nodeMap[parentPath].children = nodeMap[parentPath].children || []
            nodeMap[parentPath].children!.push(node)
          } else if (!parentPath) {
            rootNodes.push(node)
          }
        }
      })
    })

    return rootNodes
  }

  // 获取所有节点keys
  const getAllTreeKeys = (nodes: DataNode[]): React.Key[] => {
    const keys: React.Key[] = []
    const traverse = (nodeList: DataNode[]) => {
      nodeList.forEach(node => {
        keys.push(node.key)
        if (node.children) {
          traverse(node.children)
        }
      })
    }
    traverse(nodes)
    return keys
  }

  // 展开所有节点
  const handleExpandAll = () => {
    const treeData = buildTreeData(files)
    setExpandedKeys(getAllTreeKeys(treeData))
  }

  // 收起所有节点
  const handleCollapseAll = () => {
    setExpandedKeys([])
  }

  const treeData = buildTreeData(files)

  return (
    <Card
      title={title}
      size="small"
      extra={
        <Space>
          <Button
            size="small"
            type="text"
            icon={<ExpandOutlined />}
            onClick={handleExpandAll}
          >
            展开所有
          </Button>
          <Button
            size="small"
            type="text"
            icon={<CompressOutlined />}
            onClick={handleCollapseAll}
          >
            收起所有
          </Button>
        </Space>
      }
    >
      <Tree
        treeData={treeData}
        expandedKeys={expandedKeys}
        onExpand={setExpandedKeys}
        showIcon={false}
        selectable={false}
      />
    </Card>
  )
}

export default FileUploadTree