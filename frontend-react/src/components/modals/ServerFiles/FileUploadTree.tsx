import React, { useState, useMemo } from 'react'
import { ChevronRight, ChevronDown, Maximize2, Minimize2 } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import FileIcon from '@/components/files/FileIcon'
import type { FileItem } from '@/types/Server'

interface TreeNode {
  key: string
  name: string
  isLeaf: boolean
  size?: number
  children?: TreeNode[]
}

interface FileUploadTreeProps {
  files: File[]
  title?: string
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

const fileToFileItem = (name: string, path: string, isFile: boolean, size = 0, lastModified = Date.now()): FileItem => ({
  name,
  path,
  type: isFile ? 'file' : 'directory',
  size,
  modified_at: lastModified / 1000,
})

function buildTreeData(files: File[]): TreeNode[] {
  const nodeMap: Record<string, TreeNode> = {}
  const rootNodes: TreeNode[] = []

  files.forEach((file) => {
    const relativePath = (file as any).webkitRelativePath || file.name
    const pathParts = relativePath.split('/')
    let currentPath = ''

    pathParts.forEach((part: string, partIndex: number) => {
      const parentPath = currentPath
      currentPath += (currentPath ? '/' : '') + part
      const isLastPart = partIndex === pathParts.length - 1

      if (!nodeMap[currentPath]) {
        const node: TreeNode = {
          key: currentPath,
          name: part,
          isLeaf: isLastPart,
          size: isLastPart ? file.size : undefined,
          children: isLastPart ? undefined : [],
        }
        nodeMap[currentPath] = node

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

function getAllKeys(nodes: TreeNode[]): string[] {
  const keys: string[] = []
  const traverse = (list: TreeNode[]) => {
    list.forEach(node => {
      keys.push(node.key)
      if (node.children) traverse(node.children)
    })
  }
  traverse(nodes)
  return keys
}

const TreeNodeRow: React.FC<{
  node: TreeNode
  level: number
  expandedKeys: Set<string>
  onToggle: (key: string) => void
}> = ({ node, level, expandedKeys, onToggle }) => {
  const isExpanded = expandedKeys.has(node.key)
  const hasChildren = !!node.children?.length

  return (
    <>
      <div
        className="flex items-center gap-1.5 py-1 px-2 hover:bg-accent/50 rounded cursor-default"
        style={{ paddingLeft: `${level * 16 + 8}px` }}
        onClick={() => hasChildren && onToggle(node.key)}
      >
        {hasChildren ? (
          <span className="shrink-0 cursor-pointer">
            {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </span>
        ) : (
          <span className="w-3.5" />
        )}
        <span className="shrink-0">
          <FileIcon file={fileToFileItem(node.name, node.key, node.isLeaf, node.size)} />
        </span>
        <span className="text-sm">{node.name}</span>
        {node.isLeaf && node.size != null && (
          <span className="text-xs text-muted-foreground ml-1">
            ({formatFileSize(node.size)})
          </span>
        )}
      </div>
      {isExpanded && node.children?.map(child => (
        <TreeNodeRow
          key={child.key}
          node={child}
          level={level + 1}
          expandedKeys={expandedKeys}
          onToggle={onToggle}
        />
      ))}
    </>
  )
}

const FileUploadTree: React.FC<FileUploadTreeProps> = ({
  files,
  title = "待上传文件"
}) => {
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set())
  const treeData = useMemo(() => buildTreeData(files), [files])

  const handleToggle = (key: string) => {
    setExpandedKeys(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const handleExpandAll = () => {
    setExpandedKeys(new Set(getAllKeys(treeData)))
  }

  const handleCollapseAll = () => {
    setExpandedKeys(new Set())
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">{title}</CardTitle>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={handleExpandAll}>
              <Maximize2 className="mr-1 h-3.5 w-3.5" />
              展开所有
            </Button>
            <Button variant="ghost" size="sm" onClick={handleCollapseAll}>
              <Minimize2 className="mr-1 h-3.5 w-3.5" />
              收起所有
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="max-h-80 overflow-y-auto">
          {treeData.map(node => (
            <TreeNodeRow
              key={node.key}
              node={node}
              level={0}
              expandedKeys={expandedKeys}
              onToggle={handleToggle}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export default FileUploadTree
