import { buildPathTree, treeKeys, type PathTreeNode } from '@/features/files/pathTree'
import { formatFileSize } from '@/shared/utils/formatUtils'
import React, { useState, useMemo, useEffect } from 'react'
import { ChevronRight, ChevronDown, Maximize2, Minimize2 } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { Checkbox } from '@/shared/ui/checkbox'
import FileIcon from '@/features/files/components/FileIcon'
import HighlightedFileName from '@/features/files/components/HighlightedFileName'
import type { SearchFileItem } from '@/features/files/contracts'
import { matchRegex } from '@/features/files/search'

type TreeNode = PathTreeNode<SearchFileItem>

interface FileSearchResultTreeProps {
  searchResults: SearchFileItem[]
  currentRegex: string
  onSelect: (selectedKeys: React.Key[]) => void
  selectedPaths?: string[]
  onSelectionChange?: (paths: string[]) => void
}

function buildTreeData(results: SearchFileItem[]): TreeNode[] {
  return buildPathTree(results.map(result => {
    const parts = result.path.split('/').filter(Boolean)
    return { segments: parts.map((name, index) => ({ name, key: '/' + parts.slice(0, index + 1).join('/') })), payload: result }
  }))
}

const TreeNodeRow: React.FC<{
  node: TreeNode
  level: number
  expandedKeys: Set<string>
  resultsByPath: ReadonlyMap<string, SearchFileItem>
  currentRegex: string
  onToggle: (key: string) => void
  onSelect: (key: string) => void
  selectedPaths: string[]
  onSelectionChange?: (paths: string[]) => void
}> = ({ node, level, expandedKeys, resultsByPath, currentRegex, onToggle, onSelect, selectedPaths, onSelectionChange }) => {
  const isExpanded = expandedKeys.has(node.key)
  const hasChildren = !!node.children?.length

  const nodeItem = resultsByPath.get(node.key)
  const iconFile = nodeItem ?? { name: node.name, type: hasChildren ? 'directory' as const : 'file' as const }
  const matchResult = currentRegex ? matchRegex(node.name, currentRegex) : undefined
  const size = nodeItem?.type === 'file' ? nodeItem.size : undefined

  return (
    <>
      <div
        className="flex items-center gap-1.5 py-1 px-2 hover:bg-accent/50 rounded cursor-pointer"
        style={{ paddingLeft: `${level * 16 + 8}px` }}
      >
        {hasChildren ? (
          <button type="button" aria-label={`${isExpanded ? '收起' : '展开'} ${node.key}`} aria-expanded={isExpanded} className="shrink-0" onClick={() => onToggle(node.key)}>
            {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </button>
        ) : (
          <span className="w-3.5" />
        )}
        {onSelectionChange && nodeItem && <Checkbox
          aria-label={`选择搜索结果 ${node.key}`}
          checked={selectedPaths.includes(node.key)}
          onCheckedChange={checked => onSelectionChange(checked === true ? [...selectedPaths, node.key] : selectedPaths.filter(path => path !== node.key))}
        />}
        <span className="shrink-0">
          <FileIcon file={iconFile} />
        </span>
        <button type="button" className="text-left hover:underline" onClick={() => {
          if (hasChildren) onToggle(node.key)
          onSelect(node.key)
        }}><HighlightedFileName name={node.name} matchResult={matchResult} /></button>
        {size != null && (
          <span className="text-xs text-muted-foreground ml-1">
            ({formatFileSize(size, { decimals: 1, zeroValue: "0 B", terabytes: true })})
          </span>
        )}
      </div>
      {isExpanded && node.children?.map(child => (
        <TreeNodeRow
          key={child.key}
          node={child}
          level={level + 1}
          expandedKeys={expandedKeys}
          resultsByPath={resultsByPath}
          currentRegex={currentRegex}
          onToggle={onToggle}
          onSelect={onSelect}
          selectedPaths={selectedPaths}
          onSelectionChange={onSelectionChange}
        />
      ))}
    </>
  )
}

const FileSearchResultTree: React.FC<FileSearchResultTreeProps> = ({
  searchResults,
  currentRegex,
  onSelect,
  selectedPaths = [],
  onSelectionChange,
}) => {
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set())
  const treeData = useMemo(() => buildTreeData(searchResults), [searchResults])

  const resultsByPath = useMemo(() => {
    const results = new Map<string, SearchFileItem>()
    for (const result of searchResults) if (!results.has(result.path)) results.set(result.path, result)
    return results
  }, [searchResults])

  useEffect(() => {
    if (searchResults.length > 0) {
      setExpandedKeys(new Set(treeKeys(treeData)))
    } else {
      setExpandedKeys(new Set())
    }
  }, [searchResults, treeData, currentRegex])

  const handleToggle = (key: string) => {
    setExpandedKeys(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const handleSelect = (key: string) => {
    onSelect([key])
  }

  const handleExpandAll = () => {
    setExpandedKeys(new Set(treeKeys(treeData)))
  }

  const handleCollapseAll = () => {
    setExpandedKeys(new Set())
  }

  return (
    <div>
      {treeData.length > 0 && (
        <div className="mb-3 flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={handleExpandAll}>
            <Maximize2 className="mr-1 h-3.5 w-3.5" />
            展开所有
          </Button>
          <Button variant="ghost" size="sm" onClick={handleCollapseAll}>
            <Minimize2 className="mr-1 h-3.5 w-3.5" />
            收起所有
          </Button>
        </div>
      )}

      <div className="max-h-96 overflow-y-auto">
        {treeData.map(node => (
          <TreeNodeRow
            key={node.key}
            node={node}
            level={0}
            expandedKeys={expandedKeys}
            resultsByPath={resultsByPath}
            currentRegex={currentRegex}
            onToggle={handleToggle}
            onSelect={handleSelect}
            selectedPaths={selectedPaths}
            onSelectionChange={onSelectionChange}
          />
        ))}
      </div>
    </div>
  )
}

export default FileSearchResultTree
