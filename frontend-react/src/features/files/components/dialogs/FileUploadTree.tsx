import { buildPathTree, treeKeys, type PathTreeNode } from '@/features/files/pathTree'
import { formatFileSize } from '@/shared/utils/formatUtils'
import React, { useState, useMemo } from 'react'
import { ChevronRight, ChevronDown, Maximize2, Minimize2 } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card'
import { Button } from '@/shared/ui/button'
import FileIcon from '@/features/files/components/FileIcon'

type TreeNode = PathTreeNode<File>

interface FileUploadTreeProps {
  files: File[]
  title?: string
}

function buildTreeData(files: File[]): TreeNode[] {
  return buildPathTree(files.map(file => {
    const parts = (file.webkitRelativePath || file.name).split('/')
    return { segments: parts.map((name, index) => ({ name, key: parts.slice(0, index + 1).join('/') })), payload: file }
  }))
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
          <FileIcon file={{ name: node.name, type: node.isLeaf ? 'file' : 'directory' }} />
        </span>
        <span className="text-sm">{node.name}</span>
        {node.isLeaf && node.payload?.size != null && (
          <span className="text-xs text-muted-foreground ml-1">
            ({formatFileSize(node.payload?.size, { decimals: 1, zeroValue: "0 B" })})
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
    setExpandedKeys(new Set(treeKeys(treeData)))
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
