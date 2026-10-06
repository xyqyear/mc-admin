import { buildPathTree, treeKeys, type PathTreeNode } from '@/features/files/pathTree'
import { formatFileSize } from '@/shared/utils/formatUtils'
import React, { useState, useMemo } from 'react'
import { ChevronRight, ChevronDown, Maximize2, Minimize2 } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card'
import { Button } from '@/shared/ui/button'
import { Checkbox } from '@/shared/ui/checkbox'
import FileIcon from '@/features/files/components/FileIcon'
import type { OverwriteConflict } from '@/features/files/contracts'

type TreeNode = PathTreeNode<OverwriteConflict>

interface ConflictTreeProps {
  conflicts: OverwriteConflict[]
  checkedKeys: React.Key[]
  onCheck: (checked: React.Key[]) => void
  title?: string
}

function buildConflictTreeData(conflicts: OverwriteConflict[]): TreeNode[] {
  return buildPathTree(conflicts.map(conflict => {
    const parts = conflict.path.split('/')
    return { segments: parts.map((name, index) => ({ name, key: parts.slice(0, index + 1).join('/') })), payload: conflict }
  }))
}

const TreeNodeRow: React.FC<{
  node: TreeNode
  level: number
  expandedKeys: Set<string>
  checkedSet: Set<string>
  onToggle: (key: string) => void
  onCheckChange: (keys: string[], checked: boolean) => void
}> = ({ node, level, expandedKeys, checkedSet, onToggle, onCheckChange }) => {
  const isExpanded = expandedKeys.has(node.key)
  const hasChildren = !!node.children?.length
  const isChecked = checkedSet.has(node.key)

  const childLeafKeys = useMemo(() => node.children ? treeKeys([node], true) : [], [node])
  const dirChecked = hasChildren
    ? childLeafKeys.length > 0 && childLeafKeys.every(k => checkedSet.has(k))
    : isChecked
  const dirIndeterminate = hasChildren && !dirChecked && childLeafKeys.some(k => checkedSet.has(k))

  const handleDirCheck = (checked: boolean) => {
    onCheckChange(childLeafKeys, checked)
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
              onCheckChange([node.key], checked === true)
            }
          }}
        />
        <span className="shrink-0">
          <FileIcon file={{ name: node.name, type: node.payload?.type ?? 'directory' }} />
        </span>
        <span className="text-sm">{node.name}</span>
        {node.payload?.current_size != null && (
          <span className="text-xs text-muted-foreground ml-1">
            ({formatFileSize(node.payload.current_size, { decimals: 1, zeroValue: "0 B" })} → {formatFileSize(node.payload.new_size || 0, { decimals: 1, zeroValue: "0 B" })})
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

  const handleCheckChange = (keys: string[], checked: boolean) => {
    const newChecked = new Set(checkedSet)
    for (const key of keys) {
      if (checked) newChecked.add(key)
      else newChecked.delete(key)
    }
    onCheck(Array.from(newChecked))
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
