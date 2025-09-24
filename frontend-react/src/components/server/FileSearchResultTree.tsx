import React from 'react'
import { Tree, Button, Space } from 'antd'
import { ExpandOutlined, CompressOutlined } from '@ant-design/icons'
import type { DataNode } from 'antd/es/tree'
import FileIcon from '@/components/files/FileIcon'
import HighlightedFileName from '@/components/server/HighlightedFileName'
import type { FileItem } from '@/types/Server'
import type { SearchFileItem } from '@/hooks/api/fileApi'
import { matchRegex } from '@/utils/fileSearchUtils'

interface FileSearchResultTreeProps {
  searchResults: SearchFileItem[]
  currentRegex: string
  onSelect: (selectedKeys: React.Key[]) => void
}

const FileSearchResultTree: React.FC<FileSearchResultTreeProps> = ({
  searchResults,
  currentRegex,
  onSelect
}) => {
  // 内部管理展开状态
  const [expandedKeys, setExpandedKeys] = React.useState<React.Key[]>([])
  // 格式化文件大小
  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }

  // 将SearchFileItem转换为FileItem格式
  const searchResultToFileItem = (result: SearchFileItem): FileItem => ({
    name: result.name,
    path: result.path,
    type: result.type,
    size: result.size,
    modified_at: new Date(result.modified_at).getTime() / 1000
  })

  // 构建Tree数据结构
  const buildTreeData = React.useCallback((results: SearchFileItem[]): DataNode[] => {
    const nodeMap: Record<string, DataNode> = {}
    const rootNodes: DataNode[] = []

    results.forEach((result) => {
      const pathParts = result.path.split('/').filter(part => part) // 过滤空字符串

      let currentPath = ''
      pathParts.forEach((part: string, partIndex: number) => {
        const parentPath = currentPath
        currentPath += (currentPath ? '/' : '') + part
        const isLastPart = partIndex === pathParts.length - 1
        // 确保key格式与searchResults中的path格式一致（以/开头）
        const nodeKey = '/' + currentPath

        if (!nodeMap[nodeKey]) {
          const isFile = isLastPart && result.type === 'file'

          // 为文件夹创建虚拟的SearchFileItem
          const nodeItem: SearchFileItem = isLastPart ? result : {
            name: part,
            path: nodeKey, // 使用带斜杠前缀的格式
            type: 'directory',
            size: 0,
            modified_at: new Date().toISOString()
          }

          // 生成高亮匹配结果
          const matchResult = currentRegex ? matchRegex(part, currentRegex) : undefined

          const node: DataNode = {
            key: nodeKey, // 使用带斜杠前缀的格式
            title: (
              <div className="flex items-center">
                <span style={{ marginRight: 8 }}>
                  <FileIcon
                    file={searchResultToFileItem(nodeItem)}
                  />
                </span>
                <HighlightedFileName
                  name={part}
                  matchResult={matchResult}
                />
                {isFile && (
                  <span style={{ color: '#999', fontSize: '12px', marginLeft: 8 }}>
                    ({formatFileSize(result.size)})
                  </span>
                )}
              </div>
            ),
            children: isLastPart ? undefined : [],
            isLeaf: isLastPart
          }

          nodeMap[nodeKey] = node

          // 添加到父节点或根节点
          const parentKey = parentPath ? '/' + parentPath : ''
          if (parentPath && nodeMap[parentKey]) {
            nodeMap[parentKey].children = nodeMap[parentKey].children || []
            nodeMap[parentKey].children!.push(node)
          } else if (!parentPath) {
            rootNodes.push(node)
          }
        }
      })
    })

    return rootNodes
  }, [currentRegex])

  // 获取所有Tree节点的keys
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

  const treeData = React.useMemo(() => buildTreeData(searchResults), [buildTreeData, searchResults])

  // 自动展开所有节点 - 当搜索结果改变时
  React.useEffect(() => {
    if (searchResults.length > 0) {
      const allKeys = getAllTreeKeys(treeData)
      setExpandedKeys(allKeys)
    } else {
      setExpandedKeys([])
    }
  }, [searchResults, treeData])

  // 内部处理展开/收起所有节点
  const handleExpandAll = () => {
    const allKeys = getAllTreeKeys(treeData)
    setExpandedKeys(allKeys)
  }

  const handleCollapseAll = () => {
    setExpandedKeys([])
  }

  return (
    <div>
      {/* 操作按钮 */}
      {treeData.length > 0 && (
        <div className="mb-3">
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
        </div>
      )}

      {/* Tree组件 */}
      <Tree
        treeData={treeData}
        expandedKeys={expandedKeys}
        onExpand={setExpandedKeys}
        onSelect={onSelect}
        showIcon={false}
        selectable={true}
      />
    </div>
  )
}

export default FileSearchResultTree