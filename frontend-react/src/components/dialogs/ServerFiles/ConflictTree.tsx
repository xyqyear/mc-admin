import React, { useState, useMemo } from 'react'
import { ChevronRight, ChevronDown, Maximize2, Minimize2 } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import FileIcon from '@/components/files/FileIcon'
import type { OverwriteConflict } from '@/hooks/api/fileApi'
import type { FileItem } from '@/types/Server'

interface TreeNode {
  key: string
  name: string
  isLeaf: boolean
  conflict?: OverwriteConflict
  children?: TreeNode[]
}

interface ConflictTreeProps {
  conflicts: OverwriteConflict[]
  checkedKeys: React.Key[]
  onCheck: (checked: React.Key[] | { checked: React.Key[]; halfChecked: React.Key[] }) => void
  title?: string
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

const conflictToFileItem = (conflict: OverwriteConflict, name: string): FileItem => ({
  name,
  path: conflict.path,
  type: conflict.type,
  size: conflict.current_size || 0,
  modified_at: Date.now() / 1000,
})

function buildConflictTreeData(conflicts: OverwriteConflict[]): TreeNode[] {
  const nodeMap: Record<string, TreeNode> = {}
  const rootNodes: TreeNode[] = []

  conflicts.forEach((conflict) => {
    const pathParts = conflict.path.split('/')
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
          conflict: isLastPart ? conflict : undefined,
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

function getLeafKeys(nodes: TreeNode[]): string[] {
  const keys: string[] = []
  const traverse = (list: TreeNode[]) => {
    list.forEach(node => {
      if (node.isLeaf) keys.push(node.key)
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
  checkedSet: Set<string>
  onToggle: (key: string) => void
  onCheckChange: (key: string, checked: boolean) => void
}> = ({ node, level, expandedKeys, checkedSet, onToggle, onCheckChange }) => {
  const isExpanded = expandedKeys.has(node.key)
  const hasChildren = !!node.children?.length
  const isChecked = checkedSet.has(node.key)

  const childLeafKeys = useMemo(() => node.children ? getLeafKeys([node]) : [], [node])
  const dirChecked = hasChildren
    ? childLeafKeys.length > 0 && childLeafKeys.every(k => checkedSet.has(k))
    : isChecked
  const dirIndeterminate = hasChildren && !dirChecked && childLeafKeys.some(k => checkedSet.has(k))

  const handleDirCheck = (checked: boolean) => {
    childLeafKeys.forEach(k => onCheckChange(k, checked))
  }

  return (
    <>
      <div
        className="flex items-center gap-1.5 py-1 px-2 hover:bg-accent/50 rounded"
        style={{ paddingLeft: `${level * 16 + 8}px` }}
      >
        {hasChildren ? (
          <span className="shrink-0 cursor-pointer" onClick={() => onToggle(node.key)}>
            {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </span>
        ) : (
          <span className="w-3.5" />
        )}
        <Checkbox
          checked={hasChildren ? dirChecked : isChecked}
          indeterminate={dirIndeterminate}
          onCheckedChange={(checked) => {
            if (hasChildren) {
              handleDirCheck(checked === true)
            } else {
              onCheckChange(node.key, checked === true)
            }
          }}
        />
        <span className="shrink-0">
          <FileIcon file={conflictToFileItem(
            node.conflict || { path: node.key, type: 'directory', current_size: 0, new_size: 0 },
            node.name
          )} />
        </span>
        <span className="text-sm">{node.name}</span>
        {node.conflict?.current_size != null && (
          <span className="text-xs text-muted-foreground ml-1">
            ({formatFileSize(node.conflict.current_size)} → {formatFileSize(node.conflict.new_size || 0)})
          </span>
        )}
      </div>
      {isExpanded && node.children?.map(child => (
        <TreeNodeRow
          key={child.key}
          node={child}
          level={level + 1}
          expandedKeys={expandedKeys}
          checkedSet={checkedSet}
          onToggle={onToggle}
          onCheckChange={onCheckChange}
        />
      ))}
    </>
  )
}

const ConflictTree: React.FC<ConflictTreeProps> = ({
  conflicts,
  checkedKeys,
  onCheck,
  title = "冲突文件列表"
}) => {
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set())
  const treeData = useMemo(() => buildConflictTreeData(conflicts), [conflicts])
  const checkedSet = useMemo(() => new Set(checkedKeys.map(String)), [checkedKeys])

  const handleToggle = (key: string) => {
    setExpandedKeys(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const handleCheckChange = (key: string, checked: boolean) => {
    const newChecked = new Set(checkedSet)
    if (checked) newChecked.add(key)
    else newChecked.delete(key)
    onCheck(Array.from(newChecked))
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
              checkedSet={checkedSet}
              onToggle={handleToggle}
              onCheckChange={handleCheckChange}
            />
          ))}
        </div>
        <div className="mt-2 text-muted-foreground text-sm">
          默认全部选中（覆盖），取消选中表示跳过该文件
        </div>
      </CardContent>
    </Card>
  )
}

export default ConflictTree
