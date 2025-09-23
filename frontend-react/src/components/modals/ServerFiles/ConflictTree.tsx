import React, { useState } from 'react'
import { Card, Button, Tree, Space } from 'antd'
import { ExpandOutlined, CompressOutlined } from '@ant-design/icons'
import type { DataNode } from 'antd/es/tree'
import type { OverwriteConflict } from '@/hooks/api/fileApi'
import FileIcon from '@/components/files/FileIcon'
import type { FileItem } from '@/types/Server'

interface ConflictTreeProps {
  conflicts: OverwriteConflict[]
  checkedKeys: React.Key[]
  onCheck: (checked: React.Key[] | { checked: React.Key[]; halfChecked: React.Key[] }) => void
  title?: string
}

const ConflictTree: React.FC<ConflictTreeProps> = ({
  conflicts,
  checkedKeys,
  onCheck,
  title = "冲突文件列表"
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

  // 将OverwriteConflict转换为FileItem格式以便使用FileIcon
  const conflictToFileItem = (conflict: OverwriteConflict, fileName: string): FileItem => ({
    name: fileName,
    path: conflict.path,
    type: conflict.type,
    size: conflict.current_size || 0,
    modified_at: Date.now() / 1000 // 当前时间戳，因为conflict没有modified_at信息
  })

  // 将冲突列表转换为Tree数据结构
  const buildConflictTreeData = (conflicts: OverwriteConflict[]): DataNode[] => {
    const nodeMap: Record<string, DataNode> = {}
    const rootNodes: DataNode[] = []

    conflicts.forEach((conflict) => {
      const pathParts = conflict.path.split('/')

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
                  <FileIcon file={conflictToFileItem(conflict, part)} />
                </span>
                {part}
                {conflict.current_size && (
                  <span style={{ color: '#999', fontSize: '12px', marginLeft: 8 }}>
                    ({formatFileSize(conflict.current_size)} → {formatFileSize(conflict.new_size || 0)})
                  </span>
                )}
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
    const treeData = buildConflictTreeData(conflicts)
    setExpandedKeys(getAllTreeKeys(treeData))
  }

  // 收起所有节点
  const handleCollapseAll = () => {
    setExpandedKeys([])
  }

  const treeData = buildConflictTreeData(conflicts)

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
        checkable
        treeData={treeData}
        checkedKeys={checkedKeys}
        onCheck={onCheck}
        expandedKeys={expandedKeys}
        onExpand={setExpandedKeys}
        showIcon={false}
      />
      <div className="mt-2 text-gray-500 text-sm">
        默认全部选中（覆盖），取消选中表示跳过该文件
      </div>
    </Card>
  )
}

export default ConflictTree